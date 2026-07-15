#!/usr/bin/env python3
"""사업내용 텍스트 수집 (Loop 2 PART 1 텍스트 피처). ★ point-in-time 안전.

- 각 dev 기업의 **가장 이른 dev A001(사업보고서)** 원문(document.xml)을 한 번만 받는다.
  earliest filing → rcept_dt ≤ 그 기업이 채점되는 어떤 T 보다도 이르다(룩어헤드 없음).
- 원문을 flatten 해 텍스트로 저장(임베딩 캐시의 원천). 재개(resume) 가능.
출력: data/pit/features/business/business_text.parquet (corp_code, rcept_dt, text).
"""
import io
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                              # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "pit" / "features" / "business"
TXT = OUT / "business_text.parquet"
DEV_YEARS = list(range(2016, 2023))
SUBWIN = (("0101", "0315"), ("0316", "0515"))
MAXLEN = 4000                                          # 텍스트 길이 상한(캐시 절약)


def log(m):
    print(m, file=sys.stderr, flush=True)


def dev_corps():
    tp = ROOT / "data" / "pit" / "targets" / "ratios"
    corps = set()
    for y in DEV_YEARS:
        df = pd.read_parquet(tp / f"ratios_{y}.parquet")
        corps |= set(df["corp_code"])
    return corps


def earliest_rcept():
    """dev 창의 A001 사업보고서 → 기업별 최초 (rcept_no, rcept_dt). 시장전체 ledger(청크)."""
    best = {}
    for y in DEV_YEARS:
        for a, b in SUBWIN:
            page = 1
            while True:
                res = ap.get_json("list.json", {"bgn_de": f"{y}{a}", "end_de": f"{y}{b}",
                                                "pblntf_detail_ty": "A001",
                                                "page_no": str(page), "page_count": "100"})
                if res.get("status") != "000":
                    break
                for r in res.get("list", []) or []:
                    cc = (r.get("corp_code") or "").strip()
                    dt = (r.get("rcept_dt") or "").strip()
                    rn = (r.get("rcept_no") or "").strip()
                    if cc and rn and (cc not in best or dt < best[cc][1]):
                        best[cc] = (rn, dt)
                if page >= int(res.get("total_page") or 1):
                    break
                page += 1
                time.sleep(0.02)
        log(f"  ledger {y}: {len(best)} corps")
    return best


def fetch_text(rcept_no):
    blob = ap.get_raw("document.xml", {"rcept_no": rcept_no})
    if isinstance(blob, Exception) or not blob or blob[:2] != b"PK":
        return ""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""
    txt = "".join(ap.flat_text(ap._decode(zf.read(n))) for n in zf.namelist())
    return txt[:MAXLEN]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    have = {}
    if TXT.exists():
        prev = pd.read_parquet(TXT)
        have = dict(zip(prev["corp_code"], zip(prev["rcept_dt"], prev["text"])))
    corps = dev_corps()
    log(f"dev corps {len(corps)}, already {len(have)}")
    ledger = earliest_rcept()
    rows = [{"corp_code": c, "rcept_dt": have[c][0], "text": have[c][1]} for c in have]
    todo = [c for c in corps if c in ledger and c not in have]
    log(f"to fetch {len(todo)} docs")
    for i, cc in enumerate(todo, 1):
        if i % 200 == 1:                                          # 주기적 한도 점검(문서당 X)
            st = ap.get_json("fnlttSinglAcntAll.json", {"corp_code": cc, "bsns_year": "2021",
                                                        "reprt_code": "11011", "fs_div": "OFS"})
            if st.get("status") == "020":
                log("  [LIMIT] 020 한도 — 저장 후 중단(재개 가능).")
                break
        rn, dt = ledger[cc]
        txt = fetch_text(rn)
        if txt:                                                  # 실패(빈 텍스트)는 저장 안 함(재개 시 재시도)
            rows.append({"corp_code": cc, "rcept_dt": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}", "text": txt})
        if i % 200 == 0:
            pd.DataFrame(rows).to_parquet(TXT, index=False)      # 체크포인트
            log(f"  fetched {i}/{len(todo)} (kept {len(rows)})")
        time.sleep(0.03)
    pd.DataFrame(rows).to_parquet(TXT, index=False)
    log(f"business_text {len(rows)} 저장 → {TXT}")


if __name__ == "__main__":
    main()
