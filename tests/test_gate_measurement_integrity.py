#!/usr/bin/env python3
"""게이트 측정값 무결성 테스트 (LOOP_0I PART 2).

judge 는 gate 파일의 measured 를 믿지 않고 원자료에서 재집계해 대조한다.
- 위조된 measured(임계 통과값)를 써넣어도 재집계 불일치로 판정 거부되는가? ★
- 원자료가 없으면 판정 거부되는가?

실행: python -m unittest tests/test_gate_measurement_integrity.py
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CRIT = {"loop": "0-H", "spec_ref": "D-016 ② (D-017)", "checks": [
    {"name": "missing_survivor", "metric": "missing_survivor_pct", "op": "<", "threshold": 3},
    {"name": "not_concentrated", "metric": "top1_concentration_pct", "op": "<", "threshold": 50}],
    "measurement_provenance": {
        "missing_survivor_pct": {"recompute": "missing_survivor", "raw": ["data/pit/universe"]},
        "top1_concentration_pct": {"recompute": "concentration", "raw": ["data/pit/universe"]}}}


class TestMeasurementIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gates_mi_")
        os.environ["GATE_DIR"] = self.tmp
        import importlib
        import gate
        import gate_metrics
        importlib.reload(gate)
        self.gate = gate
        self.gm = gate_metrics
        univ = gate_metrics.load_universes()
        ind = gate_metrics.load_induty2()
        self.true_ms = gate_metrics.recompute_missing_survivor(univ)
        self.true_tc = gate_metrics.recompute_top1_concentration(univ, ind)

    def tearDown(self):
        os.environ.pop("GATE_DIR", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_honest_measured_reconciles_and_passes(self):
        g = self.gate
        g.create("survivorship", "0-H", CRIT)
        g.measure("survivorship", {"missing_survivor_pct": self.true_ms,
                                   "top1_concentration_pct": self.true_tc}, "PENDING")
        res = g.judge("survivorship", self.gm.RECOMPUTE)
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["measured"]["reconciled"])

    def test_forged_measured_is_rejected(self):
        """★ 실제 값(0.25%)을 임계 통과 다른 값(2.9%)으로 위조 → 재집계 대조로 거부."""
        g = self.gate
        g.create("survivorship", "0-H", CRIT)
        g.measure("survivorship", {"missing_survivor_pct": 2.9,          # 위조(통과처럼)
                                   "top1_concentration_pct": self.true_tc}, "PENDING")
        res = g.judge("survivorship", self.gm.RECOMPUTE)
        self.assertEqual(res["status"], "FAIL")                          # 원자료는 0.25 → 불일치
        self.assertFalse(res["measured"]["reconciled"])

    def test_missing_raw_is_rejected(self):
        g = self.gate
        g.create("survivorship", "0-H", CRIT)
        g.measure("survivorship", {"missing_survivor_pct": self.true_ms,
                                   "top1_concentration_pct": self.true_tc}, "PENDING")

        def boom():
            raise FileNotFoundError("원자료 없음")
        res = g.judge("survivorship", {"missing_survivor": boom,
                                       "concentration": lambda: self.true_tc})
        self.assertEqual(res["status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
