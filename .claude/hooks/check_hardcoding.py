#!/usr/bin/env python3
"""engines/ · scoring/ 의 .py에서 하드코딩 흔적을 탐지하는 검사 훅.

탐지 대상:
  - 6자리 숫자 문자열 리터럴 (종목코드 의심)
  - 알려진 기업명 문자열 리터럴
  - 비교 연산에 쓰인 매직넘버 (0, 1, -1 제외)

발견 시: `파일:라인 메시지` 출력 후 exit 1. 표준 라이브러리만 사용.

사용:
  python .claude/hooks/check_hardcoding.py            # engines/, scoring/ 전체 검사
  python .claude/hooks/check_hardcoding.py a.py b.py  # 지정 파일만 검사 (pre-commit용)
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ["engines", "scoring"]

TICKER_RE = re.compile(r"^\d{6}$")

# 회사명 리터럴은 코드에 두지 않는다 (검사기 안의 하드코딩 아이러니 제거).
# 옆의 company_names.txt 에서 읽는다. 파일이 없으면 회사명 검사만 건너뛴다.
NAMES_FILE = Path(__file__).with_name("company_names.txt")


def load_company_names():
    names = set()
    if NAMES_FILE.exists():
        for line in NAMES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line)
    return names


KNOWN_COMPANY_NAMES = load_company_names()

ALLOWED_MAGIC = {0, 1, -1}


def numeric_value(node):
    """숫자 상수 또는 -상수 형태이면 그 값을, 아니면 None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = numeric_value(node.operand)
        return -inner if inner is not None else None
    return None


def check_file(path):
    findings = []
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [(path, 0, f"파일을 읽을 수 없음: {exc}")]
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [(path, exc.lineno or 0, f"파싱 실패(구문 오류): {exc.msg}")]

    for node in ast.walk(tree):
        # 문자열 리터럴
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if TICKER_RE.match(s):
                findings.append((path, node.lineno,
                                 f"6자리 숫자 문자열 리터럴(종목코드 의심): {s!r}"))
            elif s in KNOWN_COMPANY_NAMES:
                findings.append((path, node.lineno, f"기업명 문자열 리터럴: {s!r}"))
        # 비교 연산의 매직넘버
        if isinstance(node, ast.Compare):
            for operand in [node.left, *node.comparators]:
                val = numeric_value(operand)
                if val is not None and val not in ALLOWED_MAGIC:
                    findings.append((path, node.lineno, f"비교에 쓰인 매직넘버: {val}"))
    return findings


def collect_targets(argv):
    if argv:
        return [Path(a).resolve() for a in argv if a.endswith(".py")]
    targets = []
    for d in SCAN_DIRS:
        targets.extend(sorted((ROOT / d).rglob("*.py")))
    return targets


def main():
    findings = []
    for path in collect_targets(sys.argv[1:]):
        if path.exists():
            findings.extend(check_file(path))
    if findings:
        print("하드코딩 의심 발견:")
        for path, line, msg in findings:
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            print(f"{rel}:{line}: {msg}")
        return 1
    print("check_hardcoding: 통과 (하드코딩 흔적 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
