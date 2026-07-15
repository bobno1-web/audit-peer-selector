#!/usr/bin/env python3
"""'사업의 내용' 섹션 텍스트 수집 (Loop 3 PART 1). ★ point-in-time 안전 + 캐시(api-budget).

- 각 dev 기업의 **가장 이른 dev A001(사업보고서)** 원문을 받아 "사업의 내용" 섹션만 추출.
  earliest filing → rcept_dt ≤ 그 기업이 채점되는 어떤 T 보다도 이르다(룩어헤드 없음).
- Loop 2와의 유일한 차이: 전문 첫 4000자(표지+목차)가 아니라 섹션만(section_parser, 구조적).
- ★ 캐시: 이미 수집된 corp 은 재취득 0(cache hit). ledger 도 캐시. 예상 호출·히트/미스 보고.
출력: data/pit/features/business/section_text.parquet (corp_code, rcept_dt, section_text, status).
"""
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                              # noqa: E402
import section_parser as sp                            # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "pit" / "features" / "business"
SECTXT = OUT / "section_text.parquet"
LEDGER = OUT / "ledger.parquet"
CONFIG = ROOT / "config" / "default.yaml"
DEV_YEARS = list(range(2016, 2023))                    # Loop 2 텍스트와 동일한 corp 집합
SUBWIN = (("0101", "0315"), ("0316", "0515"))


def log(m):
    print(m, file=sys.stderr, flush=True)


def dev_corps():
    tp = ROOT / "data" / "pit" / "targets" / "ratios"
    corps = set()
    for y in DEV_YEARS:
        p = tp / f"ratios_{y}.parquet"
        if p.exists():
            corps |= set(pd.read_parquet(p)["corp_code"])
    return corps


def build_ledger():
    """dev 창 A001 → 기업별 최초 (rcept_no, rcept_dt). ★ 캐시(재실행 시 crawl 0)."""
    if LEDGER.exists():
        df = pd.read_parquet(LEDGER)
        log(f"ledger cache hit: {len(df)} corps (crawl 0)")
        return dict(zip(df["corp_code"], zip(df["rcept_no"], df["rcept_dt"])))
    best, calls = {}, 0
    for y in DEV_YEARS:
        for a, b in SUBWIN:
            page = 1
            while True:
                res = ap.get_json("list.json", {"bgn_de": f"{y}{a}", "end_de": f"{y}{b}",
                                                "pblntf_detail_ty": "A001",
                                                "page_no": str(page), "page_count": "100"})
                calls += 1
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
        log(f"  ledger crawl {y}: {len(best)} corps ({calls} list calls)")
    pd.DataFrame([{"corp_code": c, "rcept_no": v[0], "rcept_dt": v[1]}
                  for c, v in best.items()]).to_parquet(LEDGER, index=False)
    return best


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    title = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["similarity"]["text_section_title"]
    have = {}
    if SECTXT.exists():
        prev = pd.read_parquet(SECTXT)
        have = {r.corp_code: (r.rcept_dt, r.section_text, r.status) for r in prev.itertuples()}
    corps = dev_corps()
    ledger = build_ledger()
    rows = [{"corp_code": c, "rcept_dt": have[c][0], "section_text": have[c][1], "status": have[c][2]}
            for c in have]
    todo = [c for c in corps if c in ledger and c not in have]
    log(f"[budget] dev_corps={len(corps)} cache_hit={len(have)} cache_miss(to_fetch)={len(todo)}")
    fetched = 0
    for i, cc in enumerate(todo, 1):
        if i % 200 == 1:                                  # 주기적 020 한도 점검
            st = ap.get_json("fnlttSinglAcntAll.json", {"corp_code": cc, "bsns_year": "2021",
                                                        "reprt_code": "11011", "fs_div": "OFS"})
            if st.get("status") == "020":
                log("  [LIMIT] 020 한도 — 저장 후 중단(재개 가능).")
                break
        rn, dt = ledger[cc]
        try:                                              # 단일 불량 문서가 전체를 죽이지 않게
            raw = ap.fetch_doc_text(rn)
            text, status = sp.extract_section(raw, title)
        except Exception as e:                            # noqa: BLE001
            text, status = "", f"error:{type(e).__name__}"
        fetched += 1
        rows.append({"corp_code": cc, "rcept_dt": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
                     "section_text": text, "status": status})
        if i % 200 == 0:
            pd.DataFrame(rows).to_parquet(SECTXT, index=False)
            log(f"  fetched {i}/{len(todo)} (ok so far)")
        time.sleep(0.03)
    df = pd.DataFrame(rows)
    df.to_parquet(SECTXT, index=False)
    n_ok = (df["status"] == "ok").sum()
    log(f"[done] section_text {len(df)} 저장. new_fetch={fetched}, cache_hit={len(have)}")
    log(f"[extract] ok={n_ok}/{len(df)} = {n_ok/max(len(df),1):.3f}; "
        f"status={df['status'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
