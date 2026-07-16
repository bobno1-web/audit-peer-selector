#!/usr/bin/env python3
"""부문별 매출 집중도 프로필 수집 (Loop 4 준비 → Loop 5 완결). ★ PIT 안전 + raw 섹션 캐시(api-budget).

- 각 dev 기업의 가장 이른 dev A001 원문(document.xml)을 받아 '사업의 내용' 섹션의 부문별 매출표에서
  집중도 프로필(seg_n, seg_top_share, seg_hhi)만 구조적으로 추출(segment_parser, 순수·검증됨).
  earliest filing → rcept_dt ≤ 그 기업이 채점되는 어떤 T → 룩어헤드 0.
- ★ Loop 5: **raw 섹션 캐시**(raw_section_cache). 섹션의 raw span(<TABLE> 구조 보존)을 디스크에 저장
  → 020 리셋 후 재실행 시 재취득 0(캐시 히트면 document.xml 미호출). Loop 3/4 의 flatten-only 캐시가
  부문표 구조를 버린 문제(SEGMENT_EXTRACTION)를 상환. (검증방 Loop4 지적 #2)
- 2겹 캐시: (1) segment_profiles.parquet = 계산결과(재계산 0), (2) raw_sections/ = 원문 섹션(재취득 0).
- document.xml 은 020 일한도 대상 — 한도 소진 시 저장 후 중단(재개 가능). 예상호출·히트/미스 보고.
- ★ fan_out 은 dev 연도만 생성한다(holdout feature 빌드 격리, Z-2).
출력: data/pit/features/segment/segment_profiles.parquet + dev 연도 segment_{y}.parquet.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                                # noqa: E402
import raw_section_cache as rc                           # noqa: E402
import segment_parser as sg                              # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUS = ROOT / "data" / "pit" / "features" / "business"
LEDGER = BUS / "ledger.parquet"
RAW_CACHE = BUS / "raw_sections"                          # ★ raw 섹션 캐시(gzip, gitignore: data/pit/**)
OUT = ROOT / "data" / "pit" / "features" / "segment"
PROFILES = OUT / "segment_profiles.parquet"
CONFIG = ROOT / "config" / "default.yaml"
SCALE = ROOT / "data" / "pit" / "features" / "scale"
DEV_YEARS = list(range(2016, 2023))                      # 부문 수집 대상 corp 집합(=dev 채점 기업)


def log(m):
    print(m, file=sys.stderr, flush=True)


def fetch_full_doc(rcept_no):
    """(full_raw_text|None, is_limit). ★ 020 한도 응답을 빈 문서로 삼키지 않고 명시적으로 구별한다.
    한 번만 취득(이중취득 방지)해 zip이면 전체 원문, 비-zip이면 020 여부 판정."""
    import io
    import zipfile
    blob = ap.get_raw("document.xml", {"rcept_no": rcept_no})
    if isinstance(blob, Exception) or not blob:
        return None, False                                 # 일시적 오류 → 결측(한도 아님)
    if blob[:2] != b"PK":                                  # zip 아님 = 오류/한도 응답
        return None, ("020" in blob[:200].decode("utf-8", "ignore"))
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        return "".join(ap._decode(zf.read(n)) for n in zf.namelist()), False
    except zipfile.BadZipFile:
        return None, False


def dev_corps():
    tp = ROOT / "data" / "pit" / "targets" / "ratios"
    corps = set()
    for y in DEV_YEARS:
        p = tp / f"ratios_{y}.parquet"
        if p.exists():
            corps |= set(pd.read_parquet(p)["corp_code"])
    return corps


def _dev_years_cfg():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return set(int(y) for y in cfg["pit_split"]["dev_years"])


def fan_out():
    """corp별 프로필 → 연도별 segment_{y}.parquet (그해 유니버스 corp 에 조인).
    ★ dev 연도만 생성한다(holdout 2023~2025 은 봉인 — feature 빌드 격리, Z-2)."""
    if not PROFILES.exists():
        return
    dev = _dev_years_cfg()
    prof = pd.read_parquet(PROFILES)
    prof = prof[prof["status"] == "ok"][["corp_code", "seg_n", "seg_top_share", "seg_hhi"]]
    made = []
    for p in sorted(SCALE.glob("scale_*.parquet")):
        y = int(p.stem.split("_")[1])
        if y not in dev:                                   # ★ holdout 연도 스킵(격리)
            continue
        corps = pd.read_parquet(p)[["corp_code"]]
        out = corps.merge(prof, on="corp_code", how="left")
        out.insert(0, "as_of_date", f"{y}-05-15")
        out.to_parquet(OUT / f"segment_{y}.parquet", index=False)
        made.append(y)
    log(f"[fan_out] dev 연도만 생성: {made} (holdout 2023~2025 미생성 — 격리)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW_CACHE.mkdir(parents=True, exist_ok=True)
    title = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["similarity"]["text_section_title"]
    if not LEDGER.exists():
        log("ledger 없음 — collect_section_text 를 먼저 실행해야 한다(A001 대장).")
        return
    ledger = {r.corp_code: (r.rcept_no, r.rcept_dt) for r in pd.read_parquet(LEDGER).itertuples()}
    have = {}
    if PROFILES.exists():
        for r in pd.read_parquet(PROFILES).itertuples():
            have[r.corp_code] = r
    corps = dev_corps()
    rows = [dict(corp_code=r.corp_code, rcept_dt=r.rcept_dt, seg_n=r.seg_n,
                 seg_top_share=r.seg_top_share, seg_hhi=r.seg_hhi, status=r.status)
            for r in have.values()]
    todo = [c for c in corps if c in ledger and c not in have]
    log(f"[budget] dev_corps={len(corps)} profile_cache_hit={len(have)} to_process={len(todo)} "
        f"(예상 document.xml 취득 ≤ {len(todo)} — raw 캐시 미스만 실제 호출)")

    new_fetch = raw_hit = fetch_err = 0
    stopped = False
    for i, cc in enumerate(todo, 1):
        rn, dt = ledger[cc]

        def producer(_rn=rn):
            raw, is_limit = fetch_full_doc(_rn)
            if is_limit:
                return None, "limit"
            if raw is None:
                return None, "error"
            return sg.raw_section_span(raw, title), "ok"

        section, outcome = rc.get_or_fetch(RAW_CACHE, cc, rn, title, producer)
        if outcome == "limit":
            log(f"  [LIMIT] 020 일한도 — 신규취득 {new_fetch}건 후 중단(재개 가능).")
            stopped = True
            break
        iso = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
        if outcome == "error":                             # 취득 실패 → 결측(임의대체 0), 재시도 안 함
            fetch_err += 1
            rows.append(dict(corp_code=cc, rcept_dt=iso, seg_n=pd.NA, seg_top_share=pd.NA,
                             seg_hhi=pd.NA, status="fetch_error"))
            time.sleep(0.03)
            continue
        raw_hit += (outcome == "hit")
        new_fetch += (outcome == "miss_fetched")
        try:
            prof, status = sg.segment_shares(section or "", title)
        except Exception as e:                             # noqa: BLE001
            prof, status = None, f"error:{type(e).__name__}"
        rows.append(dict(corp_code=cc, rcept_dt=iso,
                         seg_n=prof["seg_n"] if prof else pd.NA,
                         seg_top_share=prof["seg_top_share"] if prof else pd.NA,
                         seg_hhi=prof["seg_hhi"] if prof else pd.NA, status=status))
        if i % 200 == 0:
            pd.DataFrame(rows).to_parquet(PROFILES, index=False)
            log(f"  processed {i}/{len(todo)} (new_fetch={new_fetch}, raw_hit={raw_hit})")
        if outcome == "miss_fetched":
            time.sleep(0.03)                               # 네트워크 취득 시에만 sleep(캐시 히트는 즉시)

    df = pd.DataFrame(rows)
    if len(df):
        df.to_parquet(PROFILES, index=False)
        n_ok = int((df["status"] == "ok").sum())
        succ = n_ok / len(df) if len(df) else 0
        log(f"[done] profiles {len(df)} 저장. new_fetch={new_fetch}, raw_cache_hit={raw_hit}, "
            f"fetch_error={fetch_err}, ok={n_ok} (성공률 {succ:.3f}) stopped={stopped}")
        log(f"[cache] raw_section: hit={raw_hit} miss_fetched={new_fetch} (재실행 시 hit 로 전환 — 재취득 0)")
        log(f"[status] {df['status'].value_counts().to_dict()}")
        fan_out()
    else:
        log("[done] 프로필 0 (API 020 블록 등) — 데이터 미생성.")


if __name__ == "__main__":
    main()
