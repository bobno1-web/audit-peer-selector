#!/usr/bin/env python3
"""계정 매핑 독립 검증 (Loop 5 PART 3) — 3루프째 숙제 상환.

지금까지 검증은 '값이 DART와 같나'(data_audit: 100% 일치)만 봤다. 이 감사는 처음으로
'우리 별칭(account_aliases.yaml)이 그 비율의 **올바른 분자·분모 계정**을 골랐나'를 독립 재유도한다.

★ 독립성(개발방 별칭을 신뢰하지 않음):
  각 계정 개념을 두 독립 오라클로 재검색해 별칭의 선택과 대조한다 —
  (1) XBRL `account_id`(표준 택소노미 concept id: ifrs_Revenue/CostOfSales/GrossProfit/
      Inventories/TradeReceivables vs TradeAndOther…) — 우리 config 와 완전 독립.
  (2) 개념 키워드 broad 검색 — raw 재무제표의 모든 후보 행 나열.
  별칭이 고른 계정이 '가장 구체적(올바른)' 후보인지 규칙+증거로 판정한다.

특히 검증방 지목: 매출채권 '및기타채권' 합산선(67%), 매출원가←영업비용(5%).

표본: dev 채점 기업 40개 무작위(seed=20260716 — data_audit(20260715)와 **다른** 독립 표본).
원자료: runs/2026-07-16_mapping_audit/{summary.json, cases.csv, candidates.csv, config.yaml}.
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
import audit_parser as ap                                # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TP = ROOT / "data" / "pit" / "targets" / "ratios"
RUN = ROOT / "runs" / "2026-07-16_mapping_audit"
SEED = 20260716
N_SAMPLE = 40
DEV_YEARS = list(range(2016, 2023))
ACCOUNTS = ["매출액", "매출원가", "매출총이익", "영업이익", "재고자산", "매출채권"]
PAREN = re.compile(r"\([^()]*\)$")


def norm_id(s):
    """account_id → 소문자 영숫자만(표준 concept 매칭용). '-표준계정코드 미사용-'→''."""
    s = (s or "").lower()
    if "미사용" in s or s.strip("- ") == "":
        return ""
    return re.sub(r"[^a-z]", "", s)


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


def our_pick(rows, account, aliases, stmt):
    """생산 매핑(data_audit 와 동일 로직): sj_div 일치 + 별칭 exact-match 첫 행."""
    al = aliases.get(account, [])
    divs = stmt.get(account, [])
    for r in rows:
        nm = (r.get("account_nm") or "").replace(" ", "")
        nmb = PAREN.sub("", nm)
        if r.get("sj_div") in divs and (nm in al or nmb in al):
            v = parse_amount(r.get("thstrm_amount"))
            if v is not None:
                return {"nm": r.get("account_nm"), "id": r.get("account_id"),
                        "id_norm": norm_id(r.get("account_id")), "value": v}
    return None


# 개념 키워드(독립 broad 검색 — 별칭 목록이 아님). 각 개념의 '이상적 표준 id'도 함께.
CONCEPT = {
    "매출액":   dict(div=["IS", "CIS"], kw=["매출액", "영업수익", "수익"],
                   excl=["원가", "총이익", "총손실", "비용", "관리", "판매", "기타", "금융", "지분법"],
                   ideal_id=["revenue"]),
    "매출원가": dict(div=["IS", "CIS"], kw=["매출원가", "영업비용"], excl=[],
                   ideal_id=["costofsales"], ideal_nm=["매출원가"]),
    "매출총이익": dict(div=["IS", "CIS"], kw=["매출총이익", "매출총손실"], excl=[],
                   ideal_id=["grossprofit"]),
    "영업이익": dict(div=["IS", "CIS"], kw=["영업이익", "영업손실"], excl=["비영업"],
                   ideal_id=["operatingincome"]),
    "재고자산": dict(div=["BS"], kw=["재고자산"], excl=["평가", "충당", "변동"],
                   ideal_id=["inventories"]),
    "매출채권": dict(div=["BS"], kw=["매출채권", "수취채권", "외상매출", "받을어음"],
                   excl=["장기", "비유동"],
                   ideal_id=["tradereceivables"], combined_id=["tradeandother"],
                   combined_nm=["및기타"]),
}


def candidates(rows, account):
    """개념 키워드로 raw 재무제표의 모든 후보 행을 독립 수집(BS/IS 구분 준수)."""
    c = CONCEPT[account]
    out = []
    for r in rows:
        if r.get("sj_div") not in c["div"]:
            continue
        nm = (r.get("account_nm") or "").replace(" ", "")
        if not any(k in nm for k in c["kw"]):
            continue
        if any(x in nm for x in c.get("excl", [])):
            continue
        v = parse_amount(r.get("thstrm_amount"))
        out.append({"nm": r.get("account_nm"), "id": r.get("account_id"),
                    "id_norm": norm_id(r.get("account_id")), "value": v})
    return out


def _is_pure_receivable(cand):
    """순수 매출채권 후보인가: id 에 tradereceivables(and-other 아님) 또는 nm 이 '및기타' 없이 매출채권."""
    nm = (cand["nm"] or "").replace(" ", "")
    idn = cand["id_norm"]
    if idn:
        return "tradereceivables" in idn and "tradeandother" not in idn
    return nm in ("매출채권", "유동매출채권")


def _is_combined_receivable(cand):
    nm = (cand["nm"] or "").replace(" ", "")
    idn = cand["id_norm"]
    return ("tradeandother" in idn) or ("및기타" in nm)


def classify(account, pick, cands):
    """(verdict, note). verdict ∈ {OK, MISMAP, APPROX, DEFINITIONAL, DISCLOSURE, NO_PICK, NA}."""
    if pick is None:
        # 후보 자체가 없으면 그 기업에 그 개념이 없음(정의 안 됨) → NA. 후보는 있는데 못 고르면 NO_PICK.
        return ("NA", "개념 후보 없음(정의 안 됨)") if not cands else ("NO_PICK", "후보 있으나 별칭 미스")
    idn = pick["id_norm"]
    c = CONCEPT[account]

    if account == "매출원가":
        pnm = (pick["nm"] or "").replace(" ", "")
        if "costofsales" in idn or pnm == "매출원가" or PAREN.sub("", pnm) == "매출원가":
            return "OK", "매출원가 직접"
        # 영업비용 등으로 대체됨 — 순수 매출원가 후보가 존재했나?
        has_cogs = any(("costofsales" in x["id_norm"]) or
                       ((x["nm"] or "").replace(" ", "").startswith("매출원가")) for x in cands)
        return ("MISMAP", "매출원가 존재하나 영업비용 선택(교정 대상)") if has_cogs \
            else ("DEFINITIONAL", "매출원가 미보고 → 영업비용 대체(서비스업 관행)")

    if account == "매출채권":
        if _is_pure_receivable(pick):
            return "OK", "순수 매출채권"
        if _is_combined_receivable(pick):
            pure = any(_is_pure_receivable(x) for x in cands
                       if (x["value"] is not None and x is not pick))
            return ("APPROX", "합산선 선택(순수 매출채권도 존재 — 우선순위 교정 여지)") if pure \
                else ("DISCLOSURE", "합산선만 공시(순수 매출채권 미공시 — 공시 현실, 허용)")
        return "OK", "매출채권류"

    # 매출액/매출총이익/영업이익/재고자산: 이상적 표준 id 와 일치하면 OK
    if any(t in idn for t in c.get("ideal_id", [])):
        return "OK", f"표준 id 일치({pick['id']})"
    # 표준 id 없음(-미사용-): nm 이 개념 키워드면 OK(관행상 정상), 아니면 anomaly
    pnm = (pick["nm"] or "").replace(" ", "")
    if any(k in pnm for k in c["kw"]) and not any(x in pnm for x in c.get("excl", [])):
        return "OK", f"비표준 id 지만 계정명 정상({pick['nm']})"
    return "MISMAP", f"의심스러운 매핑: {pick['nm']} / {pick['id']}"


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

    cases, cand_rows = [], []
    verdicts = defaultdict(Counter)
    nm_used = defaultdict(Counter)
    id_used = defaultdict(Counter)
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
        for a in ACCOUNTS:
            pick = our_pick(rows, a, aliases, stmt)
            cands = candidates(rows, a)
            verdict, note = classify(a, pick, cands)
            verdicts[a][verdict] += 1
            if pick:
                nm_used[a][pick["nm"]] += 1
                id_used[a][norm_id(pick["id"]) or "(비표준)"] += 1
            cases.append({"corp_code": cc, "year": y, "account": a,
                          "our_pick_nm": pick["nm"] if pick else "",
                          "our_pick_id": pick["id"] if pick else "",
                          "our_pick_value": pick["value"] if pick else "",
                          "n_candidates": len(cands), "verdict": verdict, "note": note})
            for x in cands:
                cand_rows.append({"corp_code": cc, "year": y, "account": a,
                                  "cand_nm": x["nm"], "cand_id": x["id"], "cand_value": x["value"],
                                  "is_pick": int(bool(pick) and x["nm"] == pick["nm"]
                                                 and x["value"] == pick["value"])})
        if done % 10 == 0:
            print(f"  audited {done}", file=sys.stderr, flush=True)

    # 집계
    per_account = {}
    total_mismap = 0
    for a in ACCOUNTS:
        vc = verdicts[a]
        n = sum(vc.values())
        n_eval = n - vc.get("NA", 0)                    # 정의 안 된 케이스 제외한 평가 대상
        mismap = vc.get("MISMAP", 0) + vc.get("NO_PICK", 0)
        total_mismap += mismap
        per_account[a] = {
            "n": n, "n_evaluable": n_eval,
            "verdicts": dict(vc),
            "clear_mismap": mismap,
            "clear_mismap_rate_pct": round(100 * mismap / n_eval, 1) if n_eval else 0.0,
            "account_nm_used": dict(nm_used[a].most_common()),
            "account_id_used": dict(id_used[a].most_common()),
        }
    grand_eval = sum(per_account[a]["n_evaluable"] for a in ACCOUNTS)
    summary = {
        "meta": {"seed": SEED, "n_companies": done, "accounts": ACCOUNTS,
                 "source": "DART fnlttSinglAcntAll (독립 표본, XBRL account_id + 개념 키워드 이중 오라클)",
                 "independence": "별칭 목록 미신뢰 — account_id(표준 택소노미)와 broad 키워드로 재유도"},
        "overall_clear_mismap": total_mismap,
        "overall_clear_mismap_rate_pct": round(100 * total_mismap / grand_eval, 2) if grand_eval else 0,
        "per_account": per_account,
    }
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    with open(RUN / "cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cases[0].keys()))
        w.writeheader()
        w.writerows(cases)
    with open(RUN / "candidates.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cand_rows[0].keys()))
        w.writeheader()
        w.writerows(cand_rows)
    (RUN / "config.yaml").write_text(
        f"# mapping_audit 설정\nseed: {SEED}\nn_sample: {N_SAMPLE}\n"
        f"dev_years: [{', '.join(map(str, DEV_YEARS))}]\n"
        "source: DART fnlttSinglAcntAll 독립 표본\n"
        "method: XBRL account_id(표준 택소노미) + 개념 키워드 broad 검색으로 별칭 선택을 독립 대조\n"
        "note: data_audit(seed 20260715)와 다른 표본 — 매핑 정확성(값 아님) 독립 재유도\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
