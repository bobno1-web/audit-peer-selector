#!/usr/bin/env python3
"""holdout(2023~2025) targets 교정 재생성 (Loop 7 PART 1) — dev 와 동일 파이프라인 적용.

★ 이것은 '적용'이지 '튜닝'이 아니다: dev 에서 확정된 교정 resolver(D-026, 별칭 우선순위)를 holdout
데이터에 그대로 적용해 dev·holdout 이 **같은 파이프라인**이 되게 한다. 가중치·k·상수 재유도 0.
raw fnlttSinglAcntAll 는 raw_fin_cache 로 캐시(재실행 재취득 0). 020 → resume.

PIT: 재취득 filing 의 rcept_dt 가 원래와 다르면(정정공시) 옛 값 유지(룩어헤드 차단, dev 와 동일).
원본 백업 → runs/2026-07-16_regen_holdout/original/. 교정본을 data/pit 라이브에 직접 기록.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pit_build as pb                                      # noqa: E402  (교정 extract)
import raw_fin_cache as rfc                                 # noqa: E402
import regen_targets as RT                                  # noqa: E402  (fetch_one·CACHE·REPRT 재사용)
import provenance as PV                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
TP = PIT / "targets" / "ratios"
SP = PIT / "features" / "scale"
RUN = ROOT / "runs" / "2026-07-16_regen_holdout"
ORIG = RUN / "original"
HOLDOUT_YEARS = list(range(2023, 2026))
ACCTS = pb.FETCH


def log(m):
    print(m, file=sys.stderr, flush=True)


def firm_list():
    out = []
    for y in HOLDOUT_YEARS:
        df = pd.read_parquet(TP / f"ratios_{y}.parquet")
        df = df[df["fs_div"].fillna("").str.len() > 0]
        for _, r in df.iterrows():
            out.append((y, r["corp_code"], r["fs_div"]))
    return out


def do_fetch(firms):
    to_fetch = sum(1 for (y, cc, fs) in firms
                   if rfc.load(RT.CACHE, rfc.cache_key(cc, str(y - 1), RT.REPRT, fs)) is None)
    log(f"[budget] holdout_filed={len(firms)} cache_hit={len(firms)-to_fetch} "
        f"cache_miss={to_fetch} (예상 fnlttSinglAcntAll 취득 ≤ {to_fetch})")
    hit = miss = err = 0
    for i, (y, cc, fs) in enumerate(firms, 1):
        rows, outcome = RT.fetch_one(cc, str(y - 1), fs)
        if outcome == "hit":
            hit += 1
        elif outcome in ("miss_fetched", "empty_cached"):
            miss += 1; time.sleep(0.02)
        elif outcome == "limit":
            log(f"  [LIMIT] 020 @ {i}/{len(firms)} — 캐시 저장분 유지, 중단(resume).")
            return False
        else:
            err += 1; time.sleep(0.02)
        if i % 500 == 0:
            log(f"    fetch {i}/{len(firms)} (hit={hit} miss={miss} err={err})")
    log(f"[cache] holdout raw_fin: hit={hit} miss_fetched={miss} error={err}")
    return err == 0


def resolve_and_write(firms):
    ORIG.mkdir(parents=True, exist_ok=True)
    counts, kept_old = {}, 0
    for y in HOLDOUT_YEARS:
        cur = pd.read_parquet(TP / f"ratios_{y}.parquet")
        scur = pd.read_parquet(SP / f"scale_{y}.parquet")
        cur.to_parquet(ORIG / f"ratios_{y}.parquet", index=False)      # 백업
        scur.to_parquet(ORIG / f"scale_{y}.parquet", index=False)
        curi, scuri = cur.set_index("corp_code"), scur.set_index("corp_code")
        new_r, new_s = curi.copy(), scuri.copy()
        asof = f"{y}-05-15"
        for (yy, cc, fs) in [f for f in firms if f[0] == y]:
            rows = rfc.load(RT.CACHE, rfc.cache_key(cc, str(y - 1), RT.REPRT, fs))
            if not rows:
                continue
            fin_dt = pb.iso((rows[0].get("rcept_no") or "")[:8])
            old_rdt = str(curi.at[cc, "rcept_dt"]) if cc in curi.index else ""
            if not fin_dt or fin_dt > asof or fin_dt != old_rdt:
                kept_old += 1
                continue
            vals = pb.extract(rows)
            for a in ACCTS:
                nv = vals.get(a)
                src = curi if a in curi.columns else (scuri if a in scuri.columns else None)
                ov = src.at[cc, a] if (src is not None and cc in src.index) else None
                ov = None if (ov is None or pd.isna(ov)) else int(ov)
                if a in new_r.columns:
                    new_r.at[cc, a] = pd.NA if nv is None else nv
                if a in new_s.columns:
                    new_s.at[cc, a] = pd.NA if nv is None else nv
                if (nv or 0) != (ov or 0):
                    counts[a] = counts.get(a, 0) + 1
        for c in ACCTS:
            if c in new_r.columns:
                new_r[c] = new_r[c].astype("Int64")
            if c in new_s.columns:
                new_s[c] = new_s[c].astype("Int64")
        new_r.reset_index().to_parquet(TP / f"ratios_{y}.parquet", index=False)   # ★ 라이브 교체
        new_s.reset_index().to_parquet(SP / f"scale_{y}.parquet", index=False)
        log(f"  holdout {y}: 교정 반영")
    orig_dig = PV.combined_targets_digest(HOLDOUT_YEARS, ratios_dir=ORIG)
    corr_dig = PV.combined_targets_digest(HOLDOUT_YEARS, ratios_dir=TP)
    manifest = {"purpose": "holdout 교정 targets 출처(Loop 7)", "years": HOLDOUT_YEARS,
                "changes_by_account": counts, "kept_old_filing_changed": kept_old,
                "original_digest": orig_dig, "corrected_digest": corr_dig,
                "digest_differs": orig_dig != corr_dig,
                "per_year_corrected_digest": PV.targets_digest(HOLDOUT_YEARS, ratios_dir=TP)}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    log(json.dumps({"changes": counts, "kept_old": kept_old,
                    "digest_differs": manifest["digest_differs"]}, ensure_ascii=False))


def main():
    firms = firm_list()
    if not do_fetch(firms):
        log("중단(한도). 다음 실행 캐시 히트로 이어받기.")
        return 2
    resolve_and_write(firms)
    log("holdout targets 교정 완료 → data/pit 라이브 교체 + provenance.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
