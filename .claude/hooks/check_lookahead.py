#!/usr/bin/env python3
"""data/pit/ 접근 코드의 룩어헤드 흔적을 탐지하는 검사 훅.

탐지 대상:
  - pit 스냅샷을 as_of 시점 인자 없이 로드하는 호출
  - 미래 날짜(YYYY-MM-DD, 오늘 이후) 문자열 하드코딩

발견 시: `파일:라인 메시지` 출력 후 exit 1. 표준 라이브러리만 사용.

사용:
  python .claude/hooks/check_lookahead.py            # engines/, scoring/ 전체 검사
  python .claude/hooks/check_lookahead.py a.py b.py  # 지정 파일만 검사 (pre-commit용)
"""
import ast
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ["engines", "scoring"]

DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
PIT_HINT = "pit"
AS_OF_KEYS = {"as_of", "asof", "as_of_date"}


def call_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def mentions_pit(node):
    """호출이 pit 접근으로 보이는가 (함수명 또는 문자열 인자에 pit 흔적)."""
    if PIT_HINT in call_name(node.func).lower():
        return True
    args = [*node.args, *[kw.value for kw in node.keywords]]
    for arg in args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            v = arg.value.replace("\\", "/").lower()
            if "data/pit" in v or "/pit/" in v or v.startswith("pit/"):
                return True
    return False


def check_file(path, today):
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
        # pit 로드에 as_of 인자 없음
        if isinstance(node, ast.Call) and mentions_pit(node):
            kwnames = {kw.arg for kw in node.keywords if kw.arg}
            if not (kwnames & AS_OF_KEYS):
                findings.append((path, node.lineno,
                                 f"pit 접근에 as_of 시점 인자 없음: {call_name(node.func)}(...)"))
        # 미래 날짜 하드코딩
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for y, m, d in DATE_RE.findall(node.value):
                try:
                    dt = datetime.date(int(y), int(m), int(d))
                except ValueError:
                    continue
                if dt > today:
                    findings.append((path, node.lineno,
                                     f"미래 날짜 하드코딩(오늘 이후): {y}-{m}-{d}"))
    return findings


def collect_targets(argv):
    if argv:
        return [Path(a).resolve() for a in argv if a.endswith(".py")]
    targets = []
    for d in SCAN_DIRS:
        targets.extend(sorted((ROOT / d).rglob("*.py")))
    return targets


def main():
    today = datetime.date.today()
    findings = []
    for path in collect_targets(sys.argv[1:]):
        if path.exists():
            findings.extend(check_file(path, today))
    if findings:
        print("룩어헤드 의심 발견:")
        for path, line, msg in findings:
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            print(f"{rel}:{line}: {msg}")
        return 1
    print("check_lookahead: 통과 (룩어헤드 흔적 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
