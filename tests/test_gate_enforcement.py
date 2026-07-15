#!/usr/bin/env python3
"""게이트 강제 테스트 — 게이트가 종이가 아니라 코드인지 검사 (LOOP_0G B-4).

- 게이트 FAIL/PENDING 에서 빌드 스크립트 실행 → exit 1 인가
- 에이전트가 gate 파일을 직접 편집해 PASS 로 바꿀 수 있는가 (막혀야 함)
- create/measure 로는 PASS 가 절대 안 되는가 (approve=사람 승인만 PASS)

실행: python -m unittest tests/test_gate_enforcement.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class GateTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gates_")
        os.environ["GATE_DIR"] = self.tmp
        import importlib
        import gate
        importlib.reload(gate)                    # GATE_DIR 반영
        self.gate = gate

    def tearDown(self):
        os.environ.pop("GATE_DIR", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPassPathOnly(GateTestBase):
    def test_measure_cannot_produce_pass(self):
        g = self.gate
        g.create("x", "0-G", {"c": 1})
        self.assertEqual(g.read_gate("x")["status"], "PENDING")
        with self.assertRaises(PermissionError):     # measure 로 PASS 금지
            g.measure("x", {"m": 1}, "PASS")
        g.measure("x", {"m": 1}, "FAIL")
        self.assertFalse(g.verify("x"))              # FAIL 은 통과 아님

    def test_approve_requires_human_arg(self):
        g = self.gate
        g.create("x", "0-G", {"c": 1})
        with self.assertRaises(PermissionError):     # 빈 승인 인자 거부
            g.approve("x", "")
        self.assertFalse(g.verify("x"))
        g.approve("x", "human-says-yes")             # 사람 승인 → PASS
        self.assertTrue(g.verify("x"))
        self.assertEqual(g.read_gate("x")["decided_by"], "human")


class TestCodeJudge(GateTestBase):
    """LOOP_0H: gate.judge — 기준이 데이터로 충족되면 코드가 PASS(사람 손 approve 아님)."""
    CRIT = {"loop": "0-H", "checks": [
        {"name": "a", "metric": "m_a", "op": "<=", "threshold": 1},
        {"name": "b", "metric": "m_b", "op": "<", "threshold": 3}]}

    def test_judge_passes_when_criteria_met(self):
        g = self.gate
        g.create("s", "0-H", self.CRIT)
        g.measure("s", {"m_a": 0.0, "m_b": 0.25}, "PENDING")
        res = g.judge("s")
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["decided_by"], "gate_criteria_auto")   # 사람 아님
        self.assertTrue(g.verify("s"))

    def test_judge_fails_when_criteria_unmet(self):
        g = self.gate
        g.create("s", "0-H", self.CRIT)
        g.measure("s", {"m_a": 5.0, "m_b": 0.25}, "PENDING")        # m_a=5 > 1 → 미달
        res = g.judge("s")
        self.assertEqual(res["status"], "FAIL")
        self.assertFalse(g.verify("s"))

    def test_judge_fails_on_missing_metric(self):
        g = self.gate
        g.create("s", "0-H", self.CRIT)
        g.measure("s", {"m_a": 0.0}, "PENDING")                    # m_b 없음 → 미달
        self.assertEqual(g.judge("s")["status"], "FAIL")


class TestTamperDetection(GateTestBase):
    def test_hand_edited_pass_is_rejected(self):
        g = self.gate
        g.create("x", "0-G", {"c": 1})
        # 에이전트가 파일을 직접 열어 status 를 PASS 로 바꿔치기(서명 그대로/무효).
        p = Path(self.tmp) / "x.json"
        obj = json.loads(p.read_text(encoding="utf-8"))
        obj["status"] = "PASS"                        # 손편집 위조
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(g.verify("x"), "손편집한 PASS 가 통과됨 = 게이트 무용지물")

    def test_require_pass_exits_on_tamper(self):
        g = self.gate
        g.create("x", "0-G", {"c": 1})
        p = Path(self.tmp) / "x.json"
        obj = json.loads(p.read_text(encoding="utf-8"))
        obj["status"] = "PASS"
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            g.require_pass("x")
        self.assertEqual(cm.exception.code, 1)


class TestBuildScriptBlocked(GateTestBase):
    def _run_build(self):
        env = {**os.environ, "GATE_DIR": self.tmp, "PYTHONUTF8": "1"}
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pit_build_full.py")],
                              capture_output=True, env=env, timeout=120).returncode

    def test_build_blocked_when_pending(self):
        self.gate.create("survivorship", "0-G", {"c": 1})   # PENDING
        self.assertEqual(self._run_build(), 1, "PENDING 게이트에서 빌드가 실행됨")

    def test_build_blocked_when_fail(self):
        self.gate.create("survivorship", "0-G", {"c": 1})
        self.gate.measure("survivorship", {"m": 0}, "FAIL")
        self.assertEqual(self._run_build(), 1, "FAIL 게이트에서 빌드가 실행됨")


if __name__ == "__main__":
    unittest.main(verbosity=2)
