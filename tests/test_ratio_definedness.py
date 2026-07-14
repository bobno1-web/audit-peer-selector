#!/usr/bin/env python3
"""비율 정의성 테스트 (LOOP_0G C-3).

- 타겟별 '정의된' 비율 집합이 **재무구조**로 결정되는가 (계정 존재 + 분모>0).
- ★ 엔진이 이 집합에 영향을 줄 수 없는가 (정의성은 타겟 재무만의 함수).

실행: python -m unittest tests/test_ratio_definedness.py
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from derive_required_accounts import defined_ratios, derive_by_ratio   # noqa: E402


class TestRatioDefinedness(unittest.TestCase):
    def setUp(self):
        self.per_ratio, _, _ = derive_by_ratio()
        self.names = {r["name"] for r in self.per_ratio}

    def test_manufacturer_defines_all(self):
        mfg = {"매출액": 100, "매출원가": 60, "매출총이익": 40, "영업이익": 10,
               "재고자산": 20, "매출채권": 30}
        self.assertEqual(defined_ratios(mfg, self.per_ratio), self.names)

    def test_service_firm_excludes_inventory_ratio(self):
        # 재고자산·매출원가·매출총이익이 없는 서비스/IT/금융
        svc = {"매출액": 100, "매출원가": None, "매출총이익": None, "영업이익": 30,
               "재고자산": None, "매출채권": 25}
        d = defined_ratios(svc, self.per_ratio)
        self.assertNotIn("재고자산회전율", d)      # 재고 없음 → 정의 안 됨
        self.assertNotIn("매출총이익률", d)
        self.assertIn("영업이익률", d)              # 매출액·영업이익 있음 → 정의됨
        self.assertIn("매출채권회전율", d)

    def test_zero_denominator_excludes_ratio(self):
        z = {"매출액": 0, "매출원가": 60, "재고자산": 20, "매출채권": 30,
             "매출총이익": 40, "영업이익": 10}
        # 매출액=0(분모) → 매출총이익률·영업이익률 정의 안 됨(분모>0 아님)
        d = defined_ratios(z, self.per_ratio)
        self.assertNotIn("매출총이익률", d)
        self.assertNotIn("영업이익률", d)
        self.assertIn("재고자산회전율", d)           # 매출원가/재고자산은 유효

    def test_no_defined_ratio_is_empty(self):
        self.assertEqual(defined_ratios({"매출액": None}, self.per_ratio), set())

    def test_engine_features_cannot_change_definedness(self):
        """★ 엔진 허용 입력(산업분류·종업원수 등)을 넣어도 정의 집합이 바뀌지 않는다."""
        base = {"매출액": 100, "영업이익": 30, "매출채권": 25}
        d1 = defined_ratios(base, self.per_ratio)
        withfeat = {**base, "산업분류": "58", "종업원수": 9999, "사업내용텍스트": "x", "총자산": 500}
        d2 = defined_ratios(withfeat, self.per_ratio)
        self.assertEqual(d1, d2, "엔진 피처가 정의 비율 집합을 바꿨다 = 차단벽 붕괴")


if __name__ == "__main__":
    unittest.main(verbosity=2)
