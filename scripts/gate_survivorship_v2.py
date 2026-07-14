#!/usr/bin/env python3
"""PART D — 생존편향 게이트 v2 재판정 (LOOP_0G). ★ 측정만 한다. PASS 는 사람 승인(gate.py)만.

D-1 독립 표본(순환 차단): 상폐 기업을 **DART 거래소공시(pblntf_ty=I)의 상장폐지 관련 공시**로
  식별한다(사업보고서 이력과 독립). per-corp 조회라 3개월 제한 없음. 실제 상폐는 현재
  corp_cls∉{Y,K} 로 교차 확인(심사만 받고 생존한 기업 제외). 상폐 전 존재/상폐 후 부재 측정.

D-2 미제출-생존: 유니버스 CSV 만으로 측정. 각 T에서 "T 이전에 있었고 / T엔 없고 / T+1·T+2엔
  있는" 기업 = 그때 사업보고서를 못 냈지만 상폐 안 된(살아있는) 기업. 건수/비율/특성/쏠림.

산출: runs/2026-07-15_gate_survivorship/{summary.json, cases.csv, config.yaml}.
게이트: gate.measure 로 FAIL 또는 PENDING 만 설정(절대 PASS 아님).
"""
import csv
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                          # noqa: E402
import gate                                        # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNIV = ROOT / "data" / "pit" / "universe"
RUN = ROOT / "runs" / "2026-07-15_gate_survivorship"
SEED = 20260715
YEARS = list(range(2015, 2026))
DELIST_KW = ("상장폐지", "정리매매")               # 거래소 상폐 신호
CAND_CAP = 800                                     # 후보 스캔 상한(상폐 확인율 ~11% → n≥50 확보)
TARGET_DELISTED = 65                               # 독립 상폐 표본 목표(≥50)
GATE_ID = "survivorship"


def log(m):
    print(m, file=sys.stderr, flush=True)


def load_universes():
    univ = {}
    for y in YEARS:
        with open(UNIV / f"universe_{y}.csv", encoding="utf-8-sig") as f:
            univ[y] = {r["corp_code"]: r for r in csv.DictReader(f)}
    return univ


def delisting_disclosures(cc):
    """corp 의 거래소공시 중 상폐 관련. per-corp 라 장기간 조회 가능. (report_nm, rcept_dt) 목록."""
    out, page = [], 1
    while True:
        res = ap.get_json("list.json", {"corp_code": cc, "bgn_de": "20150101",
                                        "end_de": "20251231", "pblntf_ty": "I",
                                        "page_no": str(page), "page_count": "100"})
        if res.get("status") != "000":
            break
        for r in res.get("list", []) or []:
            nm = r.get("report_nm") or ""
            if any(k in nm for k in DELIST_KW):
                out.append((nm, (r.get("rcept_dt") or "").strip()))
        if page >= int(res.get("total_page") or 1):
            break
        page += 1
        time.sleep(0.02)
    return out


def measure_d1(univ):
    """독립 상폐 표본 → 상폐 전 존재/상폐 후 부재 측정."""
    pool = list(univ[2016].keys())                 # 2016 상장(=상폐 전 존재 전제)
    random.Random(SEED).shuffle(pool)
    delisted, scanned = [], 0
    for cc in pool:
        if len(delisted) >= TARGET_DELISTED or scanned >= CAND_CAP:
            break
        scanned += 1
        dd = delisting_disclosures(cc)
        if not dd:
            continue
        comp = ap.get_json("company.json", {"corp_code": cc})
        cls = (comp.get("corp_cls") or "").strip()
        if cls in ("Y", "K"):                      # 심사만 받고 생존 → 실제 상폐 아님. 제외.
            time.sleep(0.02)
            continue
        dyear = min(int(dt[:4]) for _, dt in dd if len(dt) >= 4)
        delisted.append({"corp_code": cc, "corp_name": univ[2016][cc]["corp_name"],
                         "delist_year": dyear, "corp_cls_now": cls,
                         "example_disclosure": dd[0][0]})
        if len(delisted) % 10 == 0:
            log(f"  D1 delisted {len(delisted)} (scanned {scanned})")
        time.sleep(0.02)

    cases = []
    success = 0
    for d in delisted:
        cc, dy = d["corp_code"], d["delist_year"]
        present_before = any(cc in univ[y] for y in YEARS if y <= dy)
        absent_2025 = cc not in univ[2025]
        absent_after_all = all(cc not in univ[y] for y in YEARS if y > dy)
        ok = present_before and absent_2025
        success += int(ok)
        cases.append({**d, "present_before": int(present_before),
                      "absent_2025": int(absent_2025), "absent_after_all": int(absent_after_all),
                      "removal_ok": int(ok)})
    rate = 100 * success / len(delisted) if delisted else 0
    return cases, scanned, round(rate, 1)


def measure_d2(univ):
    """미제출-생존: T 이전 존재 & T 부재 & (T+1 or T+2) 존재. 유니버스만으로."""
    gap_rows = []
    per_T = {}
    ever_before = defaultdict(set)                 # corp -> years present (for 'before')
    for y in YEARS:
        for cc in univ[y]:
            ever_before[cc].add(y)
    for T in range(2017, 2024):                    # 이전/이후 여유가 있는 T
        present_before = {cc for cc, ys in ever_before.items() if any(y < T for y in ys)}
        back = set(univ.get(T + 1, {})) | set(univ.get(T + 2, {}))
        gaps = [cc for cc in present_before if cc not in univ[T] and cc in back]
        per_T[T] = {"gap": len(gaps), "universe": len(univ[T]),
                    "pct": round(100 * len(gaps) / len(univ[T]), 2)}
        for cc in gaps:
            # 특성: 어느 해 데이터에서 corp_cls/stock_code (있는 해에서)
            src = univ.get(T + 1, {}).get(cc) or univ.get(T + 2, {}).get(cc) or {}
            gap_rows.append({"T": T, "corp_code": cc, "corp_name": src.get("corp_name", ""),
                             "corp_cls": src.get("corp_cls", ""), "stock_code": src.get("stock_code", "")})
    return gap_rows, per_T


def d2_characteristics(gap_rows):
    """미제출-생존 기업 특성(산업). 표본으로 induty 조회. 쏠림 판정."""
    uniq = {}
    for r in gap_rows:
        uniq.setdefault(r["corp_code"], r)
    sample = list(uniq.values())
    random.Random(SEED).shuffle(sample)
    sample = sample[:120]                          # 특성 표본
    ind = Counter()
    cls = Counter()
    for r in sample:
        comp = ap.get_json("company.json", {"corp_code": r["corp_code"]})
        ind[(comp.get("induty_code") or "NA")[:2]] += 1
        cls[r["corp_cls"] or "NA"] += 1
        time.sleep(0.02)
    top = ind.most_common(5)
    total = sum(ind.values()) or 1
    top1_share = round(100 * top[0][1] / total, 1) if top else 0
    return {"sampled": len(sample), "induty2_top5": top, "top1_share_pct": top1_share,
            "corp_cls_dist": dict(cls)}


def main():
    univ = load_universes()
    log("D-1 독립 표본 측정...")
    d1_cases, scanned, removal_rate = measure_d1(univ)
    log(f"D-1: 독립 상폐 표본 {len(d1_cases)}개, 제거율 {removal_rate}%")
    log("D-2 미제출-생존 측정...")
    gap_rows, per_T = measure_d2(univ)
    avg_pct = round(sum(v["pct"] for v in per_T.values()) / len(per_T), 2)
    log(f"D-2: 미제출-생존 평균 {avg_pct}% / 시점")
    chars = d2_characteristics(gap_rows)

    # 판정 (기준은 D-012, 결과 전 고정)
    c1 = len(d1_cases) >= 50 and removal_rate >= 95
    c2_pct = avg_pct < 3
    # 쏠림: 특정 산업 top1 점유가 과반이면 쏠림으로 본다(무작위 결측 아님)
    c2_concentrated = chars["top1_share_pct"] >= 50
    c2 = c2_pct or (not c2_concentrated)

    if not c1:
        verdict = "FAIL"
    elif c2:
        verdict = "ELIGIBLE_PENDING"               # 사람 승인 대기(스크립트는 PASS 못 만든다)
    else:
        verdict = "CONDITIONAL"                    # ②만 미달 → 보정 1회 가능

    summary = {
        "meta": {"seed": SEED, "criteria_ref": "DECISIONS D-012",
                 "sample_source": "DART 거래소공시(I) 상장폐지 + corp_cls∉{Y,K} 교차확인",
                 "note": "측정만. PASS 는 gate.py approve(사람)만."},
        "D1_independent_delisted_n": len(d1_cases),
        "D1_candidates_scanned": scanned,
        "D1_removal_rate_pct": removal_rate,
        "D1_removal_success": sum(c["removal_ok"] for c in d1_cases),
        "D1_failures": [c for c in d1_cases if not c["removal_ok"]],
        "D2_missing_survivor_by_T": per_T,
        "D2_missing_survivor_avg_pct": avg_pct,
        "D2_total_gap_events": len(gap_rows),
        "D2_characteristics": chars,
        "criteria": {"c1_removal>=95%_n>=50": c1, "c2_missing<3%": c2_pct,
                     "c2_not_concentrated": not c2_concentrated, "c2_pass": c2},
        "verdict_measured": verdict,
    }
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    with open(RUN / "cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        # D1 표본 + D2 gap 을 한 파일에(kind 로 구분)
        rows = ([{"kind": "d1_delisted", **c} for c in d1_cases] +
                [{"kind": "d2_gap", **r} for r in gap_rows])
        cols = sorted({k for r in rows for k in r})
        w = csv.DictWriter(f, fieldnames=["kind"] + [c for c in cols if c != "kind"])
        w.writeheader()
        w.writerows(rows)
    (RUN / "config.yaml").write_text(
        f"# gate_survivorship_v2 실행 설정\nseed: {SEED}\n"
        f"delist_keywords: [{', '.join(DELIST_KW)}]\ncand_cap: {CAND_CAP}\n"
        f"target_delisted: {TARGET_DELISTED}\n"
        "sample_source: DART 거래소공시(pblntf_ty=I) 상장폐지 + corp_cls 교차확인\n"
        "criteria: DECISIONS D-012 (독립 표본 >=95% / 미제출-생존 <3% or 비쏠림)\n",
        encoding="utf-8")

    # 게이트에 측정 반영 — 절대 PASS 아님(FAIL 또는 PENDING)
    measured = {"D1_removal_rate_pct": removal_rate, "D1_n": len(d1_cases),
                "D2_missing_survivor_avg_pct": avg_pct,
                "D2_top1_industry_share_pct": chars["top1_share_pct"],
                "verdict_measured": verdict}
    gate.measure(GATE_ID, measured, "FAIL" if verdict == "FAIL" else "PENDING",
                 decided_at="2026-07-15")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    log(f"측정 완료. verdict={verdict}. 게이트 status={'FAIL' if verdict=='FAIL' else 'PENDING'} "
        f"(PASS 는 사람 승인만).")


if __name__ == "__main__":
    main()
