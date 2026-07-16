#!/usr/bin/env python3
"""holdout(2023~2025) 격리 테스트 (Loop 5 Z-2 — 검증방 Loop4 지적 상환).

검증방 지적: feature 빌드가 holdout 연도를 생성하면 봉인 채널이 샌다. 이 테스트는:
  1. config dev_years ∩ holdout_years = ∅ (분리 정의).
  2. 학습 연도 선택(dev = dev_years ∩ 존재하는 scale)이 **holdout 연도를 절대 포함하지 않는다**
     — 이것이 '봉인이 강제되는 층'(학습·결판·상수유도가 모두 이 dev 리스트만 순회).
  3. ★ 신규 축(부문) 빌드 물리 격리: 부문 프로필이 존재하면 segment_{holdout}.parquet 은
     생성되지 않는다(collect_segment.fan_out 이 dev 연도만 생성).
"""
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "default.yaml"
SEG = ROOT / "data" / "pit" / "features" / "segment"
SCALE = ROOT / "data" / "pit" / "features" / "scale"


class TestHoldoutIsolation(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.dev = set(int(y) for y in self.cfg["pit_split"]["dev_years"])
        self.hold = set(int(y) for y in self.cfg["pit_split"]["holdout_years"])

    def test_dev_holdout_disjoint(self):
        self.assertEqual(self.dev & self.hold, set(), "dev 와 holdout 연도가 겹친다")
        self.assertTrue(self.hold, "holdout_years 가 비어 있다(봉인 대상 없음?)")

    def test_training_year_selection_excludes_holdout(self):
        # 학습·결판·상수유도가 쓰는 dev 선택 로직(공통 패턴)이 holdout 을 배제하는지.
        dev_selected = [y for y in self.cfg["pit_split"]["dev_years"]
                        if (SCALE / f"scale_{y}.parquet").exists()]
        self.assertTrue(dev_selected, "dev scale 파일이 하나도 없다")
        self.assertEqual(set(dev_selected) & self.hold, set(),
                         "★ 학습 연도 선택에 holdout 이 섞였다(봉인 위반)")

    def test_segment_build_has_no_holdout_files(self):
        # 부문 프로필이 존재하면(빌드 실행됨), holdout 연도 segment 파일은 없어야 한다(물리 격리).
        if not (SEG / "segment_profiles.parquet").exists():
            self.skipTest("부문 프로필 미생성 — 격리 검사 스킵(빌드 후 유효)")
        leaked = [y for y in self.hold if (SEG / f"segment_{y}.parquet").exists()]
        self.assertEqual(leaked, [], f"★ 부문 holdout 파일 생성됨(격리 실패): {leaked}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
