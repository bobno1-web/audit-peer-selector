#!/usr/bin/env python3
"""부문별 매출 집중도 프로필 수집 (Loop 4 PART 1). ★ PIT 안전 + 캐시(api-budget).

- 각 dev 기업의 가장 이른 dev A001 원문(document.xml)을 받아 '사업의 내용' 섹션의 부문별 매출표에서
  집중도 프로필(seg_n, seg_top_share, seg_hhi)만 구조적으로 추출(segment_parser, 순수·검증됨).
  earliest filing → rcept_dt ≤ 그 기업이 채점되는 어떤 T → 룩어헤드 0.
- ★ 캐시: 이미 처리한 corp 은 재취득 0. ledger 재사용(collect_section_text 와 동일). 예상호출·히트/미스 보고.
- ★ raw 테이블이 필요하다(부문표 구조). 캐시된 flatten 텍스트로는 부문 share 복원 불가(7.8%·잡음, 실증).
  document.xml 은 020 일한도 대상 — 한도 소진 시 저장 후 중단(재개 가능).
출력: data/pit/features/segment/segment_profiles.parquet + 연도 fan-out segment_{y}.parquet.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                                # noqa: E402
import segment_parser as sg                              # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUS = ROOT / "data" / "pit" / "features" / "business"
LEDGER = BUS / "ledger.parquet"
OUT = ROOT / "data" / "pit" / "features" / "segment"
PROFILES = OUT / "segment_profiles.parquet"
CONFIG = ROOT / "config" / "default.yaml"
SCALE = ROOT / "data" / "pit" / "features" / "scale"
DEV_YEARS = list(range(2016, 2023))


def log(m):
    print(m, file=sys.stderr, flush=True)


def fetch_or_limit(rcept_no):
    """(raw_text, is_limit). ★ 020 한도 응답을 빈 문서로 삼키지 않고 명시적으로 구별한다.
    한 번만 취득(이중취득 방지)해 zip이면 원문 추출, 비-zip이면 020 여부 판정."""
    import io
    import zipfile
    blob = ap.get_raw("document.xml", {"rcept_no": rcept_no})
    if isinstance(blob, Exception) or not blob:
        return "", False                                   # 일시적 오류 → 결측(한도 아님)
    if blob[:2] != b"PK":                                  # zip 아님 = 오류/한도 응답
        return "", ("020" in blob[:200].decode("utf-8", "ignore"))
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        return "".join(ap._decode(zf.read(n)) for n in zf.namelist()), False
    except zipfile.BadZipFile:
        return "", False


def dev_corps():
    tp = ROOT / "data" / "pit" / "targets" / "ratios"
    corps = set()
    for y in DEV_YEARS:
        p = tp / f"ratios_{y}.parquet"
        if p.exists():
            corps |= set(pd.read_parquet(p)["corp_code"])
    return corps


def fan_out():
    """corp별 프로필 → 연도별 segment_{y}.parquet (그해 유니버스 corp 에 조인)."""
    if not PROFILES.exists():
        return
    prof = pd.read_parquet(PROFILES)
    prof = prof[prof["status"] == "ok"][["corp_code", "seg_n", "seg_top_share", "seg_hhi"]]
    for p in SCALE.glob("scale_*.parquet"):
        y = int(p.stem.split("_")[1])
        corps = pd.read_parquet(p)[["corp_code"]]
        out = corps.merge(prof, on="corp_code", how="left")
        out.insert(0, "as_of_date", f"{y}-05-15")
        out.to_parquet(OUT / f"segment_{y}.parquet", index=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
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
    log(f"[budget] dev_corps={len(corps)} cache_hit={len(have)} cache_miss(to_fetch)={len(todo)} "
        f"(예상 document.xml 호출 = {len(todo)})")
    fetched = 0
    for i, cc in enumerate(todo, 1):
        rn, dt = ledger[cc]
        raw, is_limit = fetch_or_limit(rn)
        if is_limit:
            log(f"  [LIMIT] 020 일한도 — {fetched}건 취득 후 중단(재개 가능)."); break
        try:
            prof, status = sg.segment_shares(raw, title)
        except Exception as e:                            # noqa: BLE001
            prof, status = None, f"error:{type(e).__name__}"
        fetched += 1
        rows.append(dict(corp_code=cc, rcept_dt=f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
                         seg_n=prof["seg_n"] if prof else pd.NA,
                         seg_top_share=prof["seg_top_share"] if prof else pd.NA,
                         seg_hhi=prof["seg_hhi"] if prof else pd.NA, status=status))
        if i % 200 == 0:
            pd.DataFrame(rows).to_parquet(PROFILES, index=False)
            log(f"  fetched {i}/{len(todo)}")
        time.sleep(0.03)
    df = pd.DataFrame(rows)
    if len(df):
        df.to_parquet(PROFILES, index=False)
        n_ok = int((df["status"] == "ok").sum())
        log(f"[done] profiles {len(df)} 저장. new_fetch={fetched}, cache_hit={len(have)}, ok={n_ok}")
        fan_out()
    else:
        log("[done] 프로필 0 (API 020 블록 등) — 데이터 미생성.")


if __name__ == "__main__":
    main()
