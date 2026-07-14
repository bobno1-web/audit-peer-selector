#!/usr/bin/env python3
"""정보 차단벽 감시 훅: engines/ 코드가 채점용 데이터에 손대는지 탐지.

탐지 대상 (engines/ 하위 .py):
  - data/pit/targets 경로 참조 (채점기 전용 폴더)
  - 금지 계정명 참조 (매출원가, 매출총이익, 영업이익, 재고자산, 매출채권 등)
    = 채점 비율의 분자/분모가 되는 계정 (ORACLE.md 정보 차단벽)

발견 시: `파일:라인 메시지` 출력 후 exit 1. 표준 라이브러리만 사용.

사용:
  python .claude/hooks/check_targets_access.py            # engines/ 전체 검사
  python .claude/hooks/check_targets_access.py a.py b.py  # 지정 파일만 (pre-commit용)
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ["engines"]                       # 차단벽은 엔진 쪽에만 적용

TARGETS_PATH_HINTS = ("data/pit/targets", "pit/targets", "targets/ratios")

# 채점 비율의 분자/분모가 되는 계정 — 엔진이 이 이름을 문자열로 다루면 차단벽 위반 의심
BANNED_ACCOUNTS = (
    "매출원가", "매출총이익", "영업이익", "재고자산", "매출채권",
)


def norm(s):
    return s.replace("\\", "/").lower()


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
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            low = norm(s)
            if any(h in low for h in TARGETS_PATH_HINTS):
                findings.append((path, node.lineno,
                                 f"엔진이 채점기 전용 경로 참조(차단벽 위반): {s!r}"))
            for acct in BANNED_ACCOUNTS:
                if acct in s:
                    findings.append((path, node.lineno,
                                     f"엔진이 금지 계정명 참조(차단벽 위반): {acct!r}"))
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
        print("정보 차단벽 위반 의심 발견:")
        for path, line, msg in findings:
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            print(f"{rel}:{line}: {msg}")
        return 1
    print("check_targets_access: 통과 (엔진의 채점 데이터 접근 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
