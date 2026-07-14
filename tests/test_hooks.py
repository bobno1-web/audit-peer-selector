#!/usr/bin/env python3
"""검사 훅 회귀 테스트 — 감시견을 감시한다.

0-B/0-C에서 손으로 하던 훅 검증을 고정한다.
훅을 나중에 고치다 탐지력이 죽으면 이 테스트가 잡는다.

실행: python -m unittest tests/test_hooks.py   또는   python tests/test_hooks.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"

# 자식 프로세스가 한글을 출력해도 인코딩으로 죽지 않게 UTF-8 강제
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run_hook(hook_name, source):
    """임시 .py에 source를 써서 훅을 돌리고 exit code를 반환."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(source)
        sample = f.name
    try:
        proc = subprocess.run(
            [sys.executable, str(HOOKS / hook_name), sample],
            capture_output=True, env=CHILD_ENV,
        )
        return proc.returncode
    finally:
        os.unlink(sample)


CLEAN = (
    "def pick_peers(candidates, cfg, as_of):\n"
    "    band = cfg['band']\n"
    "    ranked = sorted(candidates, key=lambda c: c.score)\n"
    "    return ranked[:cfg['k']]\n"
)


class TestCleanCodePasses(unittest.TestCase):
    def test_clean_passes_all_hooks(self):
        for hook in ("check_hardcoding.py", "check_lookahead.py",
                     "check_targets_access.py"):
            self.assertEqual(run_hook(hook, CLEAN), 0, f"{hook} 가 clean 코드를 FAIL 처리함")


class TestHardcoding(unittest.TestCase):
    def test_ticker_literal(self):
        self.assertEqual(run_hook("check_hardcoding.py", 'x = "005930"\n'), 1)

    def test_company_name_literal(self):
        # 카카오 는 company_names.txt 에 등재됨
        self.assertEqual(run_hook("check_hardcoding.py", 'name = "카카오"\n'), 1)

    def test_magic_number_in_comparison(self):
        src = "def f(a, b):\n    return a / b > 2.0\n"
        self.assertEqual(run_hook("check_hardcoding.py", src), 1)


class TestTargetsAccess(unittest.TestCase):
    def test_targets_path_reference(self):
        src = 'p = "data/pit/targets/ratios/x.parquet"\n'
        self.assertEqual(run_hook("check_targets_access.py", src), 1)

    def test_banned_account_reference(self):
        src = 'col = "영업이익"\n'
        self.assertEqual(run_hook("check_targets_access.py", src), 1)


class TestLookahead(unittest.TestCase):
    def test_future_date_literal(self):
        self.assertEqual(run_hook("check_lookahead.py", 'd = "2099-12-31"\n'), 1)

    def test_pit_load_without_as_of(self):
        src = 'snap = load_pit("data/pit/snap.parquet")\n'
        self.assertEqual(run_hook("check_lookahead.py", src), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
