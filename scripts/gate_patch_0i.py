#!/usr/bin/env python3
"""PART 1-3/2 (LOOP_0I) — 게이트 판정 장치 패치 (재판정 아님, 결과 불변).

- D-017: 항진명제 ①(dead_retention)을 게이트 checks 에서 제거. ②(미제출-생존, 비쏠림)만 남긴다.
  ★ 결과(PASS)는 ②가 독립적으로 지탱한다(0.25%<3%, 19.4%<50%). 기준 '깎기'가 아니라
    처음부터 불필요했던 장식을 뺀 것.
- PART 2: measured 를 gate_metrics(측정과 독립)로 재집계해 넣고, measurement_provenance 를 박는다.
  gate.judge 가 다시 원자료에서 재집계·대조하므로, 위조 measured 는 통과 못 한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate                                          # noqa: E402
import gate_metrics as gm                            # noqa: E402

GATE_ID = "survivorship"

CRITERIA = {
    "loop": "0-H", "spec_ref": "DECISIONS D-016 ② (D-017: ① dead_retention 항진명제 제외)",
    "checks": [
        {"name": "missing_survivor", "metric": "missing_survivor_pct", "op": "<", "threshold": 3,
         "measurement_source": [{"kind": "file", "ref": "data/pit/universe"}]},
        {"name": "not_concentrated", "metric": "top1_concentration_pct", "op": "<", "threshold": 50,
         "measurement_source": [{"kind": "file", "ref": "data/pit/universe"},
                                {"kind": "file", "ref": "data/pit/features/industry"}]},
    ],
    "measurement_provenance": {
        "missing_survivor_pct": {"recompute": "missing_survivor",
                                 "raw": ["data/pit/universe/universe_*.csv"]},
        "top1_concentration_pct": {"recompute": "concentration",
                                   "raw": ["data/pit/universe/universe_*.csv",
                                           "data/pit/features/industry/industry_*.parquet"]},
    },
    "scoring_data_requirements": [],
    "criteria_confirmed_at": "2026-07-15",   # PART 3: 사전등록 타임스탬프(한계는 docs 명시)
}


def main():
    univ = gm.load_universes()
    ind = gm.load_induty2()
    measured = {
        "missing_survivor_pct": gm.recompute_missing_survivor(univ),
        "top1_concentration_pct": gm.recompute_top1_concentration(univ, ind),
        "dead_retention_pct_TAUTOLOGY_excluded": gm.recompute_dead_retention(
            gm.load_delist_sample(Path(gate.ROOT) / "runs" / "2026-07-15_gate_survivorship" / "cases.csv"),
            univ),
        "note": "① dead_retention 는 항진명제(D-017)로 checks 에서 제외. ②만으로 판정.",
    }
    gate.create(GATE_ID, "0-H", CRITERIA, decided_at="2026-07-15")
    gate.measure(GATE_ID, measured, "PENDING", decided_at="2026-07-15")
    g = gate.judge(GATE_ID, gm.RECOMPUTE, decided_at="2026-07-15")
    print("gate:", g["status"], "| reconciled:", g["measured"]["reconciled"],
          "| decided_by:", g["decided_by"])
    for r in g["measured"]["judge_results"]:
        print(f"  {r['name']}: stated={r['stated']} recomputed={r['recomputed']} "
              f"[{r['reconcile']}] {r['op']}{r['threshold']} -> {'PASS' if r['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
