#!/usr/bin/env python3
"""PART 0 데이터층 감사 — targets parquet 재무숫자가 DART 원본과 일치하는가 (Loop 2).

★ 지금까지 '계산이 맞나'만 봤다. '데이터 자체가 맞나'는 독립 검증된 적 없다.
표본 기업의 채점 4비율 분자·분모를 DART 에서 재취득해 parquet 과 대조한다.
각 계정에 대해 (1) 값 일치 (2) rcept_dt 시점 일치 (3) 어떤 DART account_nm 이 매핑됐나 를 기록.
매핑 오류(예: 매출원가←영업비용)를 육안 검사할 수 있게 account_nm 분포도 남긴다.
원자료: runs/2026-07-15_data_audit/{summary.json, cases.csv, config.yaml} (검증방 재대조용).
"""
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                              # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TP = ROOT / "data" / "pit" / "targets" / "ratios"
RUN = ROOT / "runs" / "2026-07-15_data_audit"
SEED = 20260715
N_SAMPLE = 40
DEV_YEARS = list(range(2016, 2023))
ACCOUNTS = ["매출액", "매출원가", "매출총이익", "영업이익", "재고자산", "매출채권"]
PAREN = re.compile(r"\([^()]*\)$")


def iso(s):
    s = str(s or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s.isdigit() else s


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


def extract_independent(rows, aliases, stmt):
    """DART 재무행에서 각 계정을 독립 추출. 반환 {acct: (value, account_nm_used)}."""
    out = {a: (None, "") for a in ACCOUNTS}
    for r in rows:
        nm = (r.get("account_nm") or "").replace(" ", "")
        nmb = PAREN.sub("", nm)
        div = r.get("sj_div")
        for a in ACCOUNTS:
            al = aliases.get(a, [])
            if out[a][0] is None and div in stmt.get(a, []) and (nm in al or nmb in al):
                v = parse_amount(r.get("thstrm_amount"))
                if v is not None:
                    out[a] = (v, r.get("account_nm"))
    return out


def scored_population():
    pop = []
    for y in DEV_YEARS:
        df = pd.read_parquet(TP / f"ratios_{y}.parquet")
        scored = df[df[ACCOUNTS].notna().any(axis=1)]
        for _, r in scored.iterrows():
            pop.append((r["corp_code"], y))
    return pop


def main():
    aliases, _, _ = ap.load_aliases()
    stmt = ap.load_statement_div()
    pop = scored_population()
    random.Random(SEED).shuffle(pop)

    cases, per_acc = [], defaultdict(lambda: {"n": 0, "match": 0, "mism": []})
    nm_used = defaultdict(Counter)
    ts_match = ts_total = 0
    done = 0
    for cc, y in pop:
        if done >= N_SAMPLE:
            break
        fy = str(y - 1)
        prow = pd.read_parquet(TP / f"ratios_{y}.parquet")
        prow = prow[prow["corp_code"] == cc]
        if not len(prow):
            continue
        prow = prow.iloc[0]
        fs = (prow.get("fs_div") or "").strip() or "OFS"
        res = ap.get_json("fnlttSinglAcntAll.json", {"corp_code": cc, "bsns_year": fy,
                                                     "reprt_code": "11011", "fs_div": fs})
        if res.get("status") != "000" and fs != "CFS":
            res = ap.get_json("fnlttSinglAcntAll.json", {"corp_code": cc, "bsns_year": fy,
                                                         "reprt_code": "11011", "fs_div": "CFS"})
        rows = res.get("list", []) or []
        if not rows:
            continue
        done += 1
        dart = extract_independent(rows, aliases, stmt)
        dart_dt = iso((rows[0].get("rcept_no") or "")[:8])
        pdt = str(prow.get("rcept_dt") or "")
        ts_total += 1
        ts_match += int(pdt == dart_dt)
        for a in ACCOUNTS:
            pv = prow.get(a)
            pv = None if pd.isna(pv) else int(pv)
            dv, dnm = dart[a]
            if dnm:
                nm_used[a][dnm] += 1
            match = (pv == dv)
            per_acc[a]["n"] += 1
            per_acc[a]["match"] += int(match)
            if not match:
                per_acc[a]["mism"].append({"corp": cc, "year": y, "parquet": pv, "dart": dv,
                                           "dart_nm": dnm})
            cases.append({"corp_code": cc, "year": y, "account": a, "parquet_value": pv,
                          "dart_value": dv, "dart_account_nm": dnm, "match": int(match),
                          "parquet_rcept_dt": pdt, "dart_rcept_dt": dart_dt})
        if done % 10 == 0:
            print(f"  audited {done}", file=sys.stderr, flush=True)

    total = sum(v["n"] for v in per_acc.values())
    matched = sum(v["match"] for v in per_acc.values())
    summary = {
        "meta": {"seed": SEED, "n_companies": done, "accounts": ACCOUNTS,
                 "source": "DART fnlttSinglAcntAll 재취득 vs data/pit/targets parquet"},
        "value_match_rate_pct": round(100 * matched / total, 2) if total else 0,
        "value_mismatch_rate_pct": round(100 * (total - matched) / total, 2) if total else 0,
        "timestamp_match_rate_pct": round(100 * ts_match / ts_total, 2) if ts_total else 0,
        "per_account": {a: {"n": per_acc[a]["n"], "match": per_acc[a]["match"],
                            "mismatch": per_acc[a]["n"] - per_acc[a]["match"],
                            "match_rate_pct": round(100 * per_acc[a]["match"] / per_acc[a]["n"], 1)
                            if per_acc[a]["n"] else 0,
                            "account_nm_used": dict(nm_used[a]),
                            "mismatch_examples": per_acc[a]["mism"][:5]} for a in ACCOUNTS},
    }
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    with open(RUN / "cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cases[0].keys()))
        w.writeheader()
        w.writerows(cases)
    (RUN / "config.yaml").write_text(
        f"# data_audit 설정\nseed: {SEED}\nn_sample: {N_SAMPLE}\n"
        f"dev_years: [{', '.join(map(str, DEV_YEARS))}]\n"
        "source: DART fnlttSinglAcntAll 재취득 vs targets parquet\n"
        "method: 독립 추출(fresh code) + account_nm 기록으로 매핑 육안검사\n", encoding="utf-8")
    print(json.dumps({"n": done, "value_match_pct": summary["value_match_rate_pct"],
                      "value_mismatch_pct": summary["value_mismatch_rate_pct"],
                      "timestamp_match_pct": summary["timestamp_match_rate_pct"],
                      "per_account_match": {a: summary["per_account"][a]["match_rate_pct"]
                                            for a in ACCOUNTS}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
