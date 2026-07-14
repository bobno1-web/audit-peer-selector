#!/usr/bin/env python3
"""엔진 격리 테스트 (정보 차단벽, LOOP_0F PART D-3).

검사:
  - engines/ 코드가 data/pit/targets 에 접근하면 탐지돼야 한다(check_targets_access 훅).
    (자기검증: 일부러 targets 를 읽는 가짜 엔진 → 반드시 exit 1.)
  - 실제 engines/ 는 위반이 없어야 한다(현재 엔진 로직 0줄).
  - ★ 데이터 차단벽: as_of(T).features 에는 채점 계정(매출총이익·영업이익·매출원가·재고자산·매출채권)이
    컬럼으로 존재하면 안 된다. (금지 목록은 config 에서 유도 — 하드코딩 없음.)

실행: python -m unittest tests/test_engine_isolation.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "check_targets_access.py"
ENGINES = ROOT / "engines"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run_hook_on(source):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(source)
        name = f.name
    try:
        return subprocess.run([sys.executable, str(HOOK), name],
                              capture_output=True, env=CHILD_ENV).returncode
    finally:
        os.unlink(name)


def _banned_target_accounts():
    """채점 계정 중 엔진 허용에 없는 것 = 금지. config 에서 유도(계정명 타이핑 없음)."""
    from derive_required_accounts import derive, load_config, CONFIG
    required = derive()[0]
    _, allowed = load_config(CONFIG)
    return [a for a in required if a not in allowed]


class TestEngineIsolation(unittest.TestCase):
    def test_hook_catches_targets_access(self):
        bad = 'p = "data/pit/targets/ratios/x.parquet"\n' \
              'df = load(p)\n'
        self.assertEqual(run_hook_on(bad), 1, "엔진이 targets 를 읽는데 훅이 못 잡음")

    def test_hook_passes_features_only(self):
        good = 'p = "data/pit/features/scale/scale_2020.parquet"\n' \
               'df = load(p)\n'
        self.assertEqual(run_hook_on(good), 0, "features 접근을 훅이 오탐")

    def test_real_engines_clean(self):
        r = subprocess.run([sys.executable, str(HOOK)], capture_output=True, env=CHILD_ENV)
        self.assertEqual(r.returncode, 0,
                         f"engines/ 에 차단벽 위반 존재:\n{r.stdout.decode('utf-8','ignore')}")

    def test_features_exclude_scoring_accounts(self):
        """데이터 차단벽: features 스냅샷에 채점 계정 컬럼이 없어야 한다."""
        from pit import as_of, EVAL_YEARS
        banned = set(_banned_target_accounts())
        self.assertTrue(banned, "금지 계정을 config 에서 못 유도")
        checked = 0
        for y in EVAL_YEARS:
            snap = as_of(f"{y}-05-15")
            if not len(snap.features):
                continue
            checked += 1
            leaked = banned & set(snap.features.columns)
            self.assertEqual(leaked, set(),
                             f"{y} features 에 채점 계정 누출: {leaked}")
        if checked == 0:
            self.skipTest("data/pit features 산출물이 없다 — pit_build.py 먼저 실행")


if __name__ == "__main__":
    unittest.main(verbosity=2)
