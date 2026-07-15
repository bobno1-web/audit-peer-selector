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


# --- [측정가능성] 검사 (LOOP_0H 1-2) : 게이트 기준이 실재 소스로 측정되는가 ---
DATA_SOURCES = ROOT / "config" / "data_sources.yaml"


def available_apis():
    """config/data_sources.yaml 의 apis 목록(실재하는 DART 엔드포인트)."""
    out, in_apis = [], False
    for raw in DATA_SOURCES.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("#") or not s:
            continue
        if s == "apis:":
            in_apis = True
            continue
        if in_apis:
            if not raw.startswith(" ") and not raw.startswith("-"):
                break
            if s.startswith("- "):
                out.append(s[2:].strip())
    return out


def source_exists(src):
    """measurement_source 항목이 실재하는가. kind: file|api|config."""
    kind, ref = src.get("kind"), src.get("ref", "")
    if kind == "file":
        return (ROOT / ref).exists()
    if kind == "api":
        return ref in available_apis()
    if kind == "config":
        return (ROOT / "config" / ref).exists()
    return False


def unmeasurable_checks(criteria):
    """게이트 criteria.checks 중 measurement_source 가 없거나 실재하지 않는 것.
    반환: [(check_name, reason)]. ★ 정책 발명·측정불가 기준을 잡는다."""
    bad = []
    for c in (criteria or {}).get("checks", []):
        srcs = c.get("measurement_source")
        name = c.get("name", c.get("metric", "?"))
        if not srcs:
            bad.append((name, "measurement_source 없음(정책 발명 의심)"))
            continue
        for s in srcs:
            if not source_exists(s):
                bad.append((name, f"소스 실재 안 함: {s}"))
    return bad


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

    # --- [측정가능성] ---
    def test_real_gates_measurement_sources_exist(self):
        gates = list(GATE_DIR.glob("*.json")) if GATE_DIR.exists() else []
        for gp in gates:
            g = json.loads(gp.read_text(encoding="utf-8"))
            crit = g.get("criteria") or {}
            if "checks" not in crit:            # 구식(pre-0-H) 게이트는 대상 아님
                continue
            self.assertEqual(unmeasurable_checks(crit), [],
                             f"{gp.name}: 측정불가 기준 {unmeasurable_checks(crit)}")

    def test_detector_catches_missing_source(self):
        crit = {"checks": [{"name": "x", "metric": "m"}]}   # measurement_source 없음
        self.assertTrue(unmeasurable_checks(crit))

    def test_detector_catches_nonexistent_api_source(self):
        # KRX 상폐일에 의존 → data_sources.yaml 에 없음 → 측정 불가
        crit = {"checks": [{"name": "removal_rate",
                            "measurement_source": [{"kind": "api", "ref": "KRX_상폐일"}]}]}
        self.assertTrue(unmeasurable_checks(crit))

    def test_d012_removal_criterion_fails_measurability(self):
        """★ H13: 0-G D-012 ①(제거율 95%)를 4번째 검사에 소급 적용 → KRX 상폐일 부재로 실패."""
        d012_c1 = {"checks": [{"name": "removal_rate>=95%",
                               "measurement_source": [{"kind": "api", "ref": "KRX_상장폐지목록"}]}]}
        bad = unmeasurable_checks(d012_c1)
        self.assertTrue(bad, "D-012 ①이 측정가능성 검사를 통과해선 안 된다(KRX 소스 부재)")

    def test_valid_sources_pass(self):
        crit = {"checks": [{"name": "ok",
                            "measurement_source": [{"kind": "api", "ref": "company.json"},
                                                   {"kind": "file", "ref": "data/pit/universe"}]}]}
        self.assertEqual(unmeasurable_checks(crit), [])

    # --- [비자명성] 항진명제 탐지 (LOOP_0I 1-2) ---
    def test_d016_dead_retention_is_tautological(self):
        """★ I2: D-016 ①(잔존율)을 항진명제 탐지에 넣으면 FAIL(=상수) 나야 한다."""
        import random
        import gate_metrics as gm
        sample = [{"corp_code": f"c{i}"} for i in range(50)]

        def make_univ(seed):
            rnd = random.Random(seed)
            return {2024: {f"c{i}" for i in range(50) if rnd.random() < 0.5},
                    2025: {f"c{i}" for i in range(50) if rnd.random() < 0.5}}
        inputs = [(sample, make_univ(s)) for s in range(10)]
        fn = lambda inp: gm.recompute_dead_retention(inp[0], inp[1])   # noqa: E731
        self.assertTrue(gm.is_tautological(fn, inputs),
                        "dead_retention 이 항진명제로 탐지되지 않음(잔존은 정의상 공집합=상수 0)")

    def test_missing_survivor_is_not_tautological(self):
        import random
        import gate_metrics as gm

        def make_univ(seed):
            rnd = random.Random(seed)
            return {y: {f"c{i}" for i in range(300) if rnd.random() < 0.7}
                    for y in range(2015, 2026)}
        inputs = [make_univ(s) for s in range(10)]
        self.assertFalse(gm.is_tautological(gm.recompute_missing_survivor, inputs),
                         "미제출-생존은 입력에 따라 변해야 함(항진명제 아님)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
