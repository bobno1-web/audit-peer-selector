#!/usr/bin/env python3
"""PART C — Point-in-Time 데이터 구축. (PART B 게이트 판단 후 진행 — D-009.)

data/pit/ 에 시점별(매년 5/15) 스냅샷을 만든다. ★ 공시일(rcept_dt) 기준 색인.
  features/scale/     매출액, 총자산            ← 엔진이 읽음(허용 입력)
  features/industry/  산업분류(induty_code)      ← 엔진이 읽음(허용 입력)
  features/business/  사업내용 텍스트(Loop2 지연) ← 구조만 + 소표본
  targets/ratios/     비율 계정(매출총이익·영업이익·매출원가·재고자산·매출채권·매출액) ← 채점기 전용
  universe/           (PART B 산출물)

원칙: 결측은 결측으로 둔다(임의값 대체 금지). 계정명은 코드가 아니라 config 에서 온다.
표본: 시점별 N_PER_YEAR 기업(재현seed). 전 유니버스 구축은 예산문제로 Loop1 재실행(DATA_CARD 명시).
"""
import csv
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd

PAREN_TAIL = re.compile(r"\([^()]*\)$")          # 말미 (손실)·(순액) 등 정규화용

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                                   # noqa: E402
from derive_required_accounts import derive, load_config, CONFIG  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
UNIV = PIT / "universe"
SEED = 20260714
EVAL_YEARS = list(range(2015, 2026))
N_PER_YEAR = 220                                            # 시점별 표본(현실 예산 내). DATA_CARD 명시.
REPRT_ANNUAL = "11011"                                      # 사업보고서
FS_ORDER = ("OFS", "CFS")                                   # 개별 우선, 연결 대체

ALIASES, _, _ = ap.load_aliases()
STMT = ap.load_statement_div()
REQUIRED = derive()[0]                                      # 타겟 계정(6) — ORACLE→config 유도
_, ALLOWED = load_config(CONFIG)
SCALE_ACCOUNTS = [a for a in ALLOWED if a in ALIASES]       # 허용∩재무계정 = 매출액,총자산
FETCH = sorted(set(REQUIRED) | set(SCALE_ACCOUNTS))         # 실제로 뽑을 계정 합집합


def log(m):
    print(m, file=sys.stderr, flush=True)


def iso(yyyymmdd):
    s = (yyyymmdd or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else ""


def parse_amount(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None


def fetch_financials(cc, fy):
    for fs in FS_ORDER:
        res = ap.get_json("fnlttSinglAcntAll.json",
                          {"corp_code": cc, "bsns_year": fy,
                           "reprt_code": REPRT_ANNUAL, "fs_div": fs})
        if res.get("status") == "000" and res.get("list"):
            return res["list"], fs
        time.sleep(0.02)
    return None, None


def extract(lst):
    """재무행 목록 → {account: amount|None}. sj_div(재무제표 구분) 준수 + 별칭 '우선순위 순서' 매칭.
    ★ Loop6 PART0(검증방 Loop5 발견): 행 순서가 아니라 '별칭 리스트 순서'로 결정한다.
      별칭은 더 구체적인 것(순수 매출채권)이 앞, 합산(매출채권및기타채권)이 뒤 → 첫 별칭이 매칭되면
      채택하므로 순수>합산 우선순위가 강제된다. 이전 로직은 응답 행 순서상 합산이 먼저 오면 합산을
      골랐다(00141389/2020: 합산 12.84B 가 순수 11.70B 앞 → 합산 오취득). 별칭순서=specificity,
      계정별 예외분기 없음(하드코딩 금지 준수)."""
    out = {a: None for a in FETCH}
    for a in FETCH:
        divs = STMT.get(a, [])
        for alias in ALIASES.get(a, []):          # 별칭 우선순위 순서(순수 → 합산)
            for r in lst:
                if r.get("sj_div") not in divs:
                    continue
                nm = (r.get("account_nm") or "").replace(" ", "")
                nmb = PAREN_TAIL.sub("", nm)       # '영업이익(손실)' → '영업이익'
                if nm == alias or nmb == alias:
                    v = parse_amount(r.get("thstrm_amount"))
                    if v is not None:
                        out[a] = v
                        break
            if out[a] is not None:
                break
    return out


def read_universe(y):
    with open(UNIV / f"universe_{y}.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_parquet(rows, path, amount_cols):
    df = pd.DataFrame(rows)
    for c in amount_cols:
        if c in df.columns:
            df[c] = df[c].astype("Int64")               # 결측 = <NA> (임의값 대체 없음)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def main():
    company_induty = {}                                  # corp_code → induty_code (캐시)
    cov = {}                                             # 커버리지 집계
    for y in EVAL_YEARS:
        fy = str(y - 1)
        asof = f"{y}-05-15"
        T = f"{y}0515"                                   # 비교용 YYYYMMDD
        univ = read_universe(y)
        rnd = random.Random(f"{SEED}-{y}")
        rnd.shuffle(univ)
        sample = univ[:N_PER_YEAR]
        scale_rows, ind_rows, tgt_rows = [], [], []
        n_fin = 0
        for rec in sample:
            cc, nm = rec["corp_code"], rec["corp_name"]
            uni_dt = iso(rec["rcept_dt"])                # A001 제출일(<=T 보장)
            lst, fs = fetch_financials(cc, fy)
            vals = {a: None for a in FETCH}
            rcept_dt = uni_dt
            if lst:
                fin_dt = iso((lst[0].get("rcept_no") or "")[:8])
                if fin_dt and fin_dt <= asof:            # ★ T 이후 정정본은 미가용 처리
                    vals = extract(lst)
                    rcept_dt = fin_dt
                    n_fin += 1
            if cc not in company_induty:
                comp = ap.get_json("company.json", {"corp_code": cc})
                company_induty[cc] = (comp.get("induty_code") or "").strip()
                time.sleep(0.02)
            induty = company_induty[cc]
            base = {"as_of_date": asof, "corp_code": cc, "corp_name": nm, "rcept_dt": rcept_dt}
            scale_rows.append({**base, "fs_div": fs or "",
                               **{a: vals[a] for a in SCALE_ACCOUNTS}})
            ind_rows.append({**base, "induty_code": induty})
            tgt_rows.append({**base, "fs_div": fs or "",
                             **{a: vals[a] for a in REQUIRED}})
            time.sleep(0.02)
        write_parquet(scale_rows, PIT / "features" / "scale" / f"scale_{y}.parquet", SCALE_ACCOUNTS)
        write_parquet(ind_rows, PIT / "features" / "industry" / f"industry_{y}.parquet", [])
        write_parquet(tgt_rows, PIT / "targets" / "ratios" / f"ratios_{y}.parquet", REQUIRED)
        cov[y] = {"sampled": len(sample), "with_financial": n_fin}
        log(f"  pit {y}: sample {len(sample)} 재무확보 {n_fin}")

    build_business_sample(company_induty)
    print_coverage(cov)


def build_business_sample(_cache):
    """사업내용 텍스트 = 사업보고서 '사업의 내용' 섹션(document.xml 원문).
    엔진 허용 입력이지만 주로 Loop 2(similarity)에서 쓴다. 전 유니버스×시점 전량 추출은
    원문 다운로드가 무거워(수만 건) **Loop 2로 지연**한다. 타당성은 0-E에서 이미 실측(96.7%).
    여기선 구조(폴더+README)만 만든다."""
    outdir = PIT / "features" / "business"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "README.md").write_text(
        "# features/business — 사업내용 텍스트 (Loop 2 지연)\n\n"
        "엔진 허용 입력 '사업내용 텍스트'. 원천 = 사업보고서 '사업의 내용' 섹션(`document.xml`).\n\n"
        "- **전량 추출은 Loop 2(similarity 엔진)로 지연.** 이유: 원문 ZIP 다운로드가 시점×유니버스\n"
        "  수만 건이라 무겁고, baseline(Loop 1)은 산업분류·규모만으로 동작한다.\n"
        "- **타당성은 이미 실측됨**: 0-E `SPIKE_UNLISTED` 에서 감사보고서 원문 텍스트 추출 96.7%.\n"
        "  같은 `audit_parser.fetch_doc_text(rcept_no)` 로 상장사 사업보고서에도 적용 가능.\n"
        "- 그때 '사업의 내용' 섹션만 정밀 추출하는 파서를 만든다(현재 파이프라인은 flat 발췌까지 실증).\n",
        encoding="utf-8")
    log("  business: 구조+README (전량 Loop2 지연, 타당성 0-E 실측)")


def print_coverage(cov):
    import json
    tot_s = sum(c["sampled"] for c in cov.values())
    tot_f = sum(c["with_financial"] for c in cov.values())
    out = {"eval_years": EVAL_YEARS, "n_per_year": N_PER_YEAR,
           "required_targets": REQUIRED, "scale_features": SCALE_ACCOUNTS,
           "per_year": cov, "total_case_years": tot_s, "total_with_financial": tot_f,
           "financial_coverage_pct": round(100 * tot_f / tot_s, 1) if tot_s else 0}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
