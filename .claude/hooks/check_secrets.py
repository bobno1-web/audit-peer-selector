#!/usr/bin/env python3
"""비밀정보(API 키) 노출 검사 훅.

탐지 대상:
  - API 키로 보이는 문자열 (40자 hex = OpenDART 키 형태) — 코드/설정 파일
  - KEY/SECRET/TOKEN/PASSWORD 류 이름에 실제 값이 대입된 흔적
  - .env 의 실제 키 값이 추적 대상 파일에 그대로 등장 (정밀 누출)
전체 스캔 모드에서는 추가로:
  - .env 가 .gitignore 로 무시되는지 확인

발견 시: `파일:라인 메시지` 출력 후 exit 1. **키 값 자체는 절대 출력하지 않는다.**
표준 라이브러리만 사용.

사용:
  python .claude/hooks/check_secrets.py            # 저장소 전체 + .gitignore 검사
  python .claude/hooks/check_secrets.py a.py b.py  # 지정 파일만 (pre-commit용)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# OpenDART 키: 40자 hex. (git SHA 오탐을 줄이려 소문자 hex 40자로 한정.)
HEX40_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{40}(?![0-9a-fA-F])")
# KEY/SECRET/TOKEN/PASSWORD = '실제값'(16자 이상, 공백·따옴표·주석 아님)
ASSIGN_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|crtfc_key)"
    r"\s*[:=]\s*['\"]?([^\s'\"#]{16,})"
)
# 대입 패턴에서 값이 이런 형태면 실제 키가 아님(플레이스홀더/환경참조).
PLACEHOLDER = re.compile(r"(?i)(your[_-]|xxx|placeholder|example|<.*>|\$\{|os\.environ|getenv)")

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
SKIP_NAMES = {".env"}                       # 실제 키 보관소. 스캔 대상 아님(.gitignore로 보호).
SKIP_SUFFIX = {".parquet", ".pyc", ".zip", ".gz", ".png", ".jpg", ".xlsx"}
# 40자 hex 오탐이 잦은 텍스트 문서는 hex40 검사에서 제외(git SHA 등). 대입패턴은 계속 검사.
HEX_SCAN_SUFFIX = {".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".sh", ".env"}


def env_secret_values():
    """.env 에서 16자 이상 값만 추출(정밀 누출 대조용). .env 없으면 빈 목록."""
    vals = []
    envp = ROOT / ".env"
    if envp.exists():
        for line in envp.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(v) >= 16:
                    vals.append(v)
    return vals


def scan_file(path, env_vals):
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [(path, 0, f"읽기 실패: {exc}")]
    do_hex = path.suffix.lower() in HEX_SCAN_SUFFIX
    for i, line in enumerate(text.splitlines(), 1):
        if do_hex and HEX40_RE.search(line):
            findings.append((path, i, "40자 hex 문자열(API 키 형태) 발견"))
        m = ASSIGN_RE.search(line)
        if m and not PLACEHOLDER.search(line):
            findings.append((path, i, f"비밀값 대입 흔적: {m.group(1)}=<redacted>"))
        for v in env_vals:                          # 실제 .env 값 정밀 대조
            if v in line:
                findings.append((path, i, ".env 의 실제 키 값이 이 파일에 노출됨"))
    return findings


def collect(argv):
    if argv:
        return [Path(a).resolve() for a in argv if Path(a).suffix]
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_NAMES or p.suffix.lower() in SKIP_SUFFIX:
            continue
        out.append(p)
    return out


def gitignore_protects_env():
    gi = ROOT / ".gitignore"
    if not gi.exists():
        return False
    for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip() == ".env":
            return True
    return False


def main():
    argv = sys.argv[1:]
    env_vals = env_secret_values()
    findings = []
    for path in collect(argv):
        if path.exists():
            findings.extend(scan_file(path, env_vals))
    full_scan = not argv
    gi_ok = True
    if full_scan:
        gi_ok = gitignore_protects_env()

    if findings or not gi_ok:
        print("비밀정보 노출 의심:")
        for path, line, msg in findings:
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            print(f"{rel}:{line}: {msg}")
        if not gi_ok:
            print(".gitignore: '.env' 무시 규칙 없음 — 키 파일이 커밋될 위험")
        return 1
    print("check_secrets: 통과 (노출 흔적 없음, .env 보호됨)" if full_scan
          else "check_secrets: 통과 (노출 흔적 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
