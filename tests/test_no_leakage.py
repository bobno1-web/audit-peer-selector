#!/usr/bin/env python3
"""정보 누출 자동 차단 테스트 (재구성 금지 원칙 강제).

config/default.yaml 의 `ratios` 각각에 대해:
  그 비율의 분자·분모 계정이 `engine_allowed_inputs` 에 **전부** 포함되면
  = 엔진 허용 입력만으로 정답을 재구성할 수 있다 = 누출 → FAIL.

핵심: 계정/비율 목록을 코드에 하드코딩하지 않고 **config 를 읽어 기계적으로** 검사한다.
따라서 앞으로 누가 config 에 누출 비율(예: 총자산회전율)을 추가하면 자동으로 FAIL 난다.

실행: python -m unittest tests/test_no_leakage.py   또는   python tests/test_no_leakage.py
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "default.yaml"


def load_config(path):
    """config 의 ratios(list of {name,numerator,denominator}) 와
    engine_allowed_inputs(list) 만 뽑는 최소 파서 (PyYAML 의존 없음)."""
    ratios, allowed = [], []
    section, cur = None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]          # 주석 제거
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):        # 블록 키
            section, cur = stripped[:-1].strip(), None
            continue
        if indent == 0 and ":" in stripped:               # 스칼라 최상위 키
            section = None
            continue
        if section == "ratios":
            if stripped.startswith("- "):
                cur = {}
                ratios.append(cur)
                rest = stripped[2:].strip()
                if ":" in rest:
                    kk, vv = rest.split(":", 1)
                    cur[kk.strip()] = vv.strip()
            elif ":" in stripped and cur is not None:
                kk, vv = stripped.split(":", 1)
                cur[kk.strip()] = vv.strip()
        elif section == "engine_allowed_inputs":
            if stripped.startswith("- "):
                allowed.append(stripped[2:].strip())
    return ratios, allowed


def accounts_of(ratio):
    accts = set()
    for key in ("numerator", "denominator"):
        v = ratio.get(key)
        if v:
            accts.add(v)
    return accts


def find_leaks(ratios, allowed):
    """분자·분모 계정이 전부 허용 목록에 있는(=재구성 가능) 비율 이름 목록."""
    allowset = set(allowed)
    leaks = []
    for r in ratios:
        accts = accounts_of(r)
        if accts and accts.issubset(allowset):
            leaks.append(r.get("name", "<unnamed>"))
    return leaks


class TestNoLeakage(unittest.TestCase):
    def test_real_config_has_no_leak(self):
        ratios, allowed = load_config(CONFIG)
        self.assertTrue(ratios, "config 에서 ratios 를 못 읽었다(파서/파일 확인)")
        self.assertTrue(allowed, "config 에서 engine_allowed_inputs 를 못 읽었다")
        leaks = find_leaks(ratios, allowed)
        self.assertEqual(leaks, [], f"누출 비율 감지: {leaks} (엔진 허용 입력만으로 재구성 가능)")

    def test_detector_catches_injected_leak(self):
        # 감시견이 살아있는지 확인: 총자산회전율(매출액÷총자산; 둘 다 허용) 주입 → 반드시 감지
        _, allowed = load_config(CONFIG)
        injected = [{"name": "총자산회전율", "numerator": "매출액", "denominator": "총자산"}]
        self.assertEqual(find_leaks(injected, allowed), ["총자산회전율"],
                         "누출 탐지기가 총자산회전율을 못 잡는다 = 무용지물")


def _cli():
    ratios, allowed = load_config(CONFIG)
    leaks = find_leaks(ratios, allowed)
    if leaks:
        print(f"LEAK DETECTED: {leaks}")
        return 1
    print(f"no leakage. ratios={[r.get('name') for r in ratios]} allowed={allowed}")
    return 0


if __name__ == "__main__":
    if "--cli" in sys.argv:
        sys.exit(_cli())
    unittest.main(verbosity=2)
