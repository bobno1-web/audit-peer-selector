#!/usr/bin/env python3
"""스파이크 원자료 보존 강제 테스트.

runs/ 의 모든 spike 폴더에 summary.json + cases.csv + config.yaml 이
전부 있는지 검사한다. 하나라도 없으면 FAIL.
→ 0-E의 universe 스파이크가 원자료를 안 남긴 것 같은 사고를 기계로 잡는다.
(근거: skill spike_protocol, 0-E 검증 지적 #3)

실행: python -m unittest tests/test_run_artifacts.py  또는  python tests/test_run_artifacts.py
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
REQUIRED = ("summary.json", "cases.csv", "config.yaml")


def spike_dirs():
    """runs/ 하위에서 'spike' 가 이름에 든 폴더(원자료 보존 대상)."""
    if not RUNS.exists():
        return []
    return [d for d in RUNS.iterdir() if d.is_dir() and "spike" in d.name.lower()]


class TestRunArtifacts(unittest.TestCase):
    def test_every_spike_has_artifacts(self):
        dirs = spike_dirs()
        self.assertTrue(dirs, "runs/ 에 spike 폴더가 하나도 없다(경로/명명 확인)")
        missing = []
        for d in dirs:
            for f in REQUIRED:
                if not (d / f).exists():
                    missing.append(f"{d.name}/{f}")
        self.assertEqual(missing, [], f"스파이크 원자료 누락: {missing}")

    def test_cases_csv_nonempty(self):
        for d in spike_dirs():
            csv = d / "cases.csv"
            if csv.exists():
                lines = [ln for ln in csv.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
                self.assertGreater(len(lines), 1, f"{d.name}/cases.csv 에 데이터 행이 없다(헤더뿐)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
