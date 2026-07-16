#!/usr/bin/env python3
"""산출물 정교화 계층 테스트 (Loop 8) — 신뢰등급이 채점비율 실제값을 안 쓰는지(T2) 강제.

peer 신뢰등급은 응집도(엔진 유사도)만의 함수여야 한다(정답 훔쳐보기 금지). 구조적으로 grade() 가
(cohesion, thresholds)만 받고 비율값 인자가 없음을 실증 + 단조성(응집도↑ 시 등급 안 내려감).
"""
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scoring" / "oracle"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines" / "similarity"))
import build_report as BR                                   # noqa: E402


class TestReportLayer(unittest.TestCase):
    def test_grade_signature_has_no_ratio_value(self):
        # ★ grade() 는 (cohesion, thr)만 받는다 — 채점비율 실제값을 입력으로 받지 않음(구조적 증거).
        params = list(inspect.signature(BR.grade).parameters)
        self.assertEqual(params, ["cohesion", "thr"],
                         "★ 신뢰등급이 응집도 외 값을 받으면 정답 훔쳐보기 위험")

    def test_grade_pure_and_monotone(self):
        thr = {"q33": 0.4, "q67": 0.6}
        self.assertEqual(BR.grade(0.30, thr), "LOW")
        self.assertEqual(BR.grade(0.40, thr), "MEDIUM")   # 경계 포함
        self.assertEqual(BR.grade(0.50, thr), "MEDIUM")
        self.assertEqual(BR.grade(0.60, thr), "HIGH")
        self.assertEqual(BR.grade(0.90, thr), "HIGH")
        # 단조: 응집도가 오르면 등급이 내려가지 않는다
        rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        vals = [rank[BR.grade(c, thr)] for c in [0.1, 0.3, 0.4, 0.5, 0.6, 0.8]]
        self.assertEqual(vals, sorted(vals), "★ 응집도↑ 시 등급이 내려가면 안 됨")


if __name__ == "__main__":
    unittest.main(verbosity=2)
