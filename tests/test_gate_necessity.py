#!/usr/bin/env python3
"""게이트 필요성 테스트 (LOOP_0G C-6).

게이트가 **채점-데이터 요건**을 발명하는 것을 코드가 막는다.
- 채점에 쓰이는 데이터 요건은 ORACLE→config에서 유도된 **비율 계정**뿐이다(fetch_accounts).
- 게이트 criteria 의 `scoring_data_requirements` 가 그 집합 밖의 계정을 요구하면 = 발명 → FAIL.
  근거: 0-D "종업원수 필수"(종업원수는 채점 계정 아님) / 0-F "6계정 전부"(발명된 요건).

실행: python -m unittest tests/test_gate_necessity.py
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from derive_required_accounts import fetch_accounts        # noqa: E402

GATE_DIR = ROOT / "runs" / "gates"


def scoring_vocab():
    """채점이 실제로 쓰는 데이터 요건 = ORACLE 비율 계정(유도). 이 밖은 발명."""
    return set(fetch_accounts())


def invented_requirements(reqs):
    """reqs 중 채점 어휘에 없는 것(=발명된 채점 요건)."""
    vocab = scoring_vocab()
    return [r for r in reqs if r not in vocab]


class TestGateNecessity(unittest.TestCase):
    def test_real_gates_have_no_invented_scoring_requirement(self):
        gates = list(GATE_DIR.glob("*.json")) if GATE_DIR.exists() else []
        for gp in gates:
            g = json.loads(gp.read_text(encoding="utf-8"))
            reqs = (g.get("criteria") or {}).get("scoring_data_requirements", [])
            self.assertEqual(invented_requirements(reqs), [],
                             f"{gp.name}: 발명된 채점 요건 {invented_requirements(reqs)}")

    def test_detector_catches_employees(self):
        # 0-D: 종업원수는 채점 계정이 아니다(피처). 채점 요건으로 넣으면 발명.
        self.assertEqual(invented_requirements(["종업원수"]), ["종업원수"])

    def test_detector_catches_made_up_account(self):
        self.assertEqual(invented_requirements(["영업권상각비"]), ["영업권상각비"])

    def test_real_scoring_accounts_pass(self):
        self.assertEqual(invented_requirements(sorted(scoring_vocab())), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
