#!/usr/bin/env python3
"""PIT 무결성 테스트 (Loop 0의 최종 관문, LOOP_0F PART D).

검사:
  - 빌드가 rcept_dt(제출일) 기준으로 색인됐는가: 스냅샷 T 의 모든 행 rcept_dt <= T (F21/C-3).
  - as_of(date) 가 미래(rcept_dt > date) 행을 거르는가 — 무작위 시점 100개.
  - features/targets 의 기업이 그 시점 universe 안에 있는가.
  - ★ D-2 자기검증: 미래 데이터 한 행을 주입하면 탐지되는가(안 잡히면 무용지물).

실행: python -m unittest tests/test_pit_integrity.py
"""
import random
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pit import as_of, pit_violations, EVAL_YEARS               # noqa: E402
from pit.reader import PIT, _read_parquet                       # noqa: E402

SNAP = "-05-15"
LAYERS = (("features/scale", "scale"), ("features/industry", "industry"),
          ("targets/ratios", "ratios"))


def _years_with_data():
    return [y for y in EVAL_YEARS
            if (PIT / "targets" / "ratios" / f"ratios_{y}.parquet").exists()]


class TestPITIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.years = _years_with_data()
        if not cls.years:
            raise unittest.SkipTest("data/pit 산출물이 없다 — pit_build.py 먼저 실행")

    def test_build_indexed_by_rcept_dt(self):
        """빌드 산출물: 스냅샷 T 의 모든 rcept_dt <= T (제출일 색인, 룩어헤드 없음)."""
        for y in self.years:
            asof = f"{y}{SNAP}"
            for sub, stem in LAYERS:
                df = _read_parquet(PIT / sub / f"{stem}_{y}.parquet")
                if len(df):
                    bad = pit_violations(df, asof)
                    self.assertEqual(len(bad), 0,
                                     f"{stem}_{y}: rcept_dt > {asof} 인 행 {len(bad)}개(룩어헤드)")

    def test_asof_filters_future_random_dates(self):
        """as_of(date) 는 rcept_dt <= date 만 반환 — 무작위 100개 시점."""
        rnd = random.Random(20260714)
        for _ in range(100):
            y = rnd.choice(EVAL_YEARS)
            date = f"{y}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"
            snap = as_of(date, with_targets=True)
            for df, label in ((snap.features, "features"), (snap.targets, "targets")):
                if len(df):
                    self.assertEqual(len(pit_violations(df, date)), 0,
                                     f"as_of({date}) {label} 에 미래 행 존재")

    def test_universe_membership(self):
        """features/targets 의 기업은 그 시점 universe 안에 있어야 한다."""
        for y in self.years:
            snap = as_of(f"{y}{SNAP}", with_targets=True)
            if not len(snap.universe):
                continue
            uset = set(snap.universe["corp_code"].astype(str))
            for df, label in ((snap.features, "features"), (snap.targets, "targets")):
                if len(df):
                    outside = set(df["corp_code"].astype(str)) - uset
                    self.assertEqual(outside, set(),
                                     f"{y} {label}: universe 밖 기업 {len(outside)}개")

    def test_injected_future_row_is_detected(self):
        """★ D-2: 미래 데이터 주입 시 반드시 FAIL(탐지)이 나야 한다."""
        y = self.years[0]
        asof = f"{y}{SNAP}"
        snap = as_of(asof, with_targets=True)
        base = snap.targets if len(snap.targets) else snap.features
        self.assertTrue(len(base) > 0, "주입 테스트용 실데이터가 없음")
        # 주입 전: 실데이터엔 위반이 없어야 한다.
        self.assertEqual(len(pit_violations(base, asof)), 0, "실데이터에 이미 미래 행이 있음")
        # 미래 rcept_dt 한 행 주입.
        row = base.iloc[[0]].copy()
        row.loc[row.index, "rcept_dt"] = "2099-12-31"
        injected = pd.concat([base, row], ignore_index=True)
        self.assertGreaterEqual(len(pit_violations(injected, asof)), 1,
                                "미래 행을 주입했는데 탐지 못함 = 무결성 검사 무용지물")


if __name__ == "__main__":
    unittest.main(verbosity=2)
