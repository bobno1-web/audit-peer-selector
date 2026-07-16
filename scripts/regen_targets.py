#!/usr/bin/env python3
"""dev targets 재생성 (Loop 6 PART 0-3) — 매출채권 매핑 버그 교정 후 재채점 기반.

교정된 pit_build.extract(별칭 우선순위: 순수 매출채권 > 합산)로 dev(2016~2022) targets/scale 을
재생성한다. raw fnlttSinglAcntAll 응답은 raw_fin_cache 로 캐시 → 재실행 시 재취득 0(api-budget).

★ 재취득 대상 = 현재 targets 에 fs_div 가 기록된(재무 확보) 기업만. 각 firm-year 1콜(기록된 fs_div 직접).
★ PIT 격리: 재취득 filing 의 rcept_dt 가 원래와 **다르면**(정정공시 유입) 그 기업은 **옛 값 유지**
   (룩어헤드/정정 오염 차단). 오직 '같은 filing 을 새 resolver 로 재해석'한 차이만 남긴다.
★ holdout(2023~2025) 은 재생성하지 않는다(미개봉; 개봉 시 함께 재생성).
★ 결측 무대체. 스테이징(runs/…/staged) 에 쓴 뒤 diff 검토 후 라이브 스왑(별도).

resume: 020 한도 시 캐시까지 저장하고 중단 → 다음 실행은 캐시 히트로 이어받음.
사용: python scripts/regen_targets.py           # fetch(+가능하면 resolve/stage/diff)
"""
import gzip
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                                   # noqa: E402
import pit_build as pb                                      # noqa: E402  (교정된 extract 포함)
import raw_fin_cache as rfc                                 # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
TP = PIT / "targets" / "ratios"
SP = PIT / "features" / "scale"
CACHE = PIT / "cache" / "raw_fin"                           # gitignore 대상(무거움)
RUN = ROOT / "runs" / "2026-07-16_regen_targets"
DEV_YEARS = list(range(2016, 2023))
REPRT = "11011"
ACCTS = pb.FETCH                                            # 재해석 대상 계정(REQUIRED ∪ SCALE)


def log(m):
    print(m, file=sys.stderr, flush=True)


def firm_list():
    """(y, corp_code, corp_name, fs_div, rcept_dt) — fs_div 기록된(재무확보) dev firm-year."""
    out = []
    for y in DEV_YEARS:
        df = pd.read_parquet(TP / f"ratios_{y}.parquet")
        df = df[df["fs_div"].fillna("").str.len() > 0]
        for _, r in df.iterrows():
            out.append((y, r["corp_code"], r["corp_name"], r["fs_div"], r["rcept_dt"]))
    return out


def fetch_one(cc, fy, fs):
    """raw_fin_cache 계약용 producer 로 감싼 취득. (rows|None, outcome)."""
    def producer():
        res = ap.get_json("fnlttSinglAcntAll.json",
                          {"corp_code": cc, "bsns_year": fy, "reprt_code": REPRT, "fs_div": fs})
        st = res.get("status")
        if st == "000":
            return res.get("list", []) or [], "000"
        return None, st
    return rfc.get_or_fetch(CACHE, cc, fy, REPRT, fs, producer)


def do_fetch(firms):
    """캐시 우선 취득. 020 → 중단(resume). 반환 outcome 카운터, hit_all(bool)."""
    hit = miss = empty = err = 0
    # 예상 호출 수 로그(api-budget 규칙 4): 캐시 미리 조회
    to_fetch = 0
    for (y, cc, nm, fs, rdt) in firms:
        key = rfc.cache_key(cc, str(y - 1), REPRT, fs)
        if rfc.load(CACHE, key) is None:
            to_fetch += 1
    log(f"[budget] dev_filed={len(firms)} cache_hit={len(firms) - to_fetch} "
        f"cache_miss={to_fetch} (예상 fnlttSinglAcntAll 취득 ≤ {to_fetch})")
    for i, (y, cc, nm, fs, rdt) in enumerate(firms, 1):
        rows, outcome = fetch_one(cc, str(y - 1), fs)
        if outcome == "hit":
            hit += 1
        elif outcome == "miss_fetched":
            miss += 1
            time.sleep(0.02)
        elif outcome == "empty_cached":
            empty += 1
            time.sleep(0.02)
        elif outcome == "limit":
            log(f"  [LIMIT] status=020 한도초과 @ {i}/{len(firms)} — 캐시 저장분까지 유지, 중단(resume).")
            return {"hit": hit, "miss_fetched": miss, "empty": empty, "error": err}, False
        else:
            err += 1
            time.sleep(0.02)
        if i % 500 == 0:
            log(f"    fetch {i}/{len(firms)} (hit={hit} miss={miss} empty={empty} err={err})")
    log(f"[cache] raw_fin: hit={hit} miss_fetched={miss} empty={empty} error={err}")
    return {"hit": hit, "miss_fetched": miss, "empty": empty, "error": err}, (err == 0)


def resolve_and_stage(firms):
    """캐시에서 재해석 → staged parquet + diff. PIT: filing 변동 기업은 옛 값 유지."""
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "staged").mkdir(exist_ok=True)
    diff_rows = []
    kept_old = 0
    for y in DEV_YEARS:
        cur = pd.read_parquet(TP / f"ratios_{y}.parquet").set_index("corp_code")
        scur = pd.read_parquet(SP / f"scale_{y}.parquet").set_index("corp_code")
        asof = f"{y}-05-15"
        new_ratio = cur.copy()
        new_scale = scur.copy()
        yf = [(cc, fs) for (yy, cc, nm, fs, rdt) in firms if yy == y]
        for cc, fs in yf:
            key = rfc.cache_key(cc, str(y - 1), REPRT, fs)
            rows = rfc.load(CACHE, key)
            if not rows:                                    # 무자료/미취득 → 옛 값 유지
                continue
            fin_dt = pb.iso((rows[0].get("rcept_no") or "")[:8])
            old_rdt = str(cur.at[cc, "rcept_dt"]) if cc in cur.index else ""
            if not fin_dt or fin_dt > asof or fin_dt != old_rdt:
                kept_old += 1                               # ★ filing 변동/룩어헤드 → 옛 값 유지(오염 차단)
                continue
            vals = pb.extract(rows)                         # 교정된 resolver
            for a in ACCTS:
                nv = vals.get(a)
                # ★ 옛 값은 그 계정의 '올바른 소스' 파케이에서(ratios 에 없는 총자산은 scale 에서).
                #   이전 버그: 총자산 old 를 ratios 에서 읽어 항상 None → 거짓 변경 카운트.
                src = cur if a in cur.columns else (scur if a in scur.columns else None)
                ov = src.at[cc, a] if (src is not None and cc in src.index) else None
                ov = None if (ov is None or pd.isna(ov)) else int(ov)
                if a in new_ratio.columns:
                    new_ratio.at[cc, a] = pd.NA if nv is None else nv
                if a in new_scale.columns:
                    new_scale.at[cc, a] = pd.NA if nv is None else nv
                if (nv or 0) != (ov or 0):
                    diff_rows.append({"year": y, "corp_code": cc, "account": a,
                                      "old": ov, "new": nv})
        for c in ACCTS:
            if c in new_ratio.columns:
                new_ratio[c] = new_ratio[c].astype("Int64")
            if c in new_scale.columns:
                new_scale[c] = new_scale[c].astype("Int64")
        new_ratio.reset_index().to_parquet(RUN / "staged" / f"ratios_{y}.parquet", index=False)
        new_scale.reset_index().to_parquet(RUN / "staged" / f"scale_{y}.parquet", index=False)
        log(f"  staged {y}: firms {len(yf)}")
    dd = pd.DataFrame(diff_rows)
    dd.to_csv(RUN / "diff.csv", index=False, encoding="utf-8-sig")
    by_acct = dd.groupby("account").size().to_dict() if len(dd) else {}
    changed_firms = dd[["year", "corp_code"]].drop_duplicates().shape[0] if len(dd) else 0
    summary = {"dev_years": DEV_YEARS, "n_firm_years_filed": len(firms),
               "kept_old_filing_changed": kept_old,
               "n_account_changes": len(dd), "n_firm_years_changed": changed_firms,
               "changes_by_account": by_acct}
    (RUN / "regen_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    log(json.dumps(summary, ensure_ascii=False))
    return summary


def main():
    firms = firm_list()
    counts, ok = do_fetch(firms)
    if not ok and counts.get("error", 0) == 0:
        # 020 로 중단됨(정상 resume 경로)
        log("중단(한도). 다음 실행 시 캐시 히트로 이어받기.")
        return 2
    resolve_and_stage(firms)
    log("regen 완료 → runs/2026-07-16_regen_targets/staged/*.parquet + diff.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
