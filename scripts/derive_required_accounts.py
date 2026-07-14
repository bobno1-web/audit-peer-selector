#!/usr/bin/env python3
"""필수 계정 집합을 기계적으로 유도한다 (사람이 목록을 타이핑하지 않는다).

ORACLE.md 의 채점 비율 이름 → config/default.yaml 의 비율→계정 매핑 → 필수 계정 집합(분자·분모의 합집합).
채점 비율에 안 쓰이는 계정(피처 전용)은 필수에서 자동으로 빠진다.

실행: python scripts/derive_required_accounts.py            # 콘솔 출력
      python scripts/derive_required_accounts.py --write    # docs/REQUIRED_ACCOUNTS.md 갱신
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "docs" / "ORACLE.md"
CONFIG = ROOT / "config" / "default.yaml"
OUT = ROOT / "docs" / "REQUIRED_ACCOUNTS.md"


def load_config(path):
    """config 의 ratios(list of {name,numerator,denominator}) 와 engine_allowed_inputs(list)."""
    ratios, allowed, section, cur = [], [], None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            section, cur = stripped[:-1].strip(), None
            continue
        if indent == 0 and ":" in stripped:
            section = None
            continue
        if section == "ratios":
            if stripped.startswith("- "):
                cur = {}
                ratios.append(cur)
                rest = stripped[2:].strip()
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    cur[k.strip()] = v.strip()
            elif ":" in stripped and cur is not None:
                k, v = stripped.split(":", 1)
                cur[k.strip()] = v.strip()
        elif section == "engine_allowed_inputs":
            if stripped.startswith("- "):
                allowed.append(stripped[2:].strip())
    return ratios, allowed


def derive():
    oracle_text = ORACLE.read_text(encoding="utf-8")
    ratios, allowed = load_config(CONFIG)
    required, used_ratios, missing_in_oracle = set(), [], []
    for r in ratios:
        name = r.get("name")
        if not name:
            continue
        used_ratios.append(name)
        # ORACLE 이 권위. config 비율명이 ORACLE 에 있어야 그 매핑을 신뢰한다.
        if name not in oracle_text:
            missing_in_oracle.append(name)
            continue
        for key in ("numerator", "denominator"):
            if r.get(key):
                required.add(r[key])
    # 엔진 허용 입력 중 채점에 안 쓰이는 것 = 필수 아님(피처 전용). config 에서 계산(하드코딩 없음).
    feature_only = [a for a in allowed if a not in required]
    return sorted(required), used_ratios, feature_only, missing_in_oracle


def render_md(required, used_ratios, feature_only, missing):
    lines = [
        "# REQUIRED_ACCOUNTS — 필수 계정 (자동 유도)",
        "",
        "> ★ 이 파일은 `scripts/derive_required_accounts.py` 의 **산출물**이다. **손으로 편집 금지.**",
        "> 갱신: `python scripts/derive_required_accounts.py --write`.",
        "",
        "유도 경로: `docs/ORACLE.md` 채점 비율 → `config/default.yaml` 비율→계정 매핑 → 분자·분모 합집합.",
        "",
        f"## 채점 비율 ({len(used_ratios)}개)",
        "".join(f"\n- {n}" for n in used_ratios),
        "",
        f"## 필수 계정 ({len(required)}개)",
        "".join(f"\n- {a}" for a in required),
        "",
        "## 필수 아님 — 엔진 허용 입력 중 채점 비율에 안 쓰이는 것 (피처 전용)",
        "  없다고 그 기업을 버리지 않는다. (config `engine_allowed_inputs` 에서 자동 계산)",
        "".join(f"\n- {a}" for a in feature_only),
    ]
    if missing:
        lines += ["", f"## ⚠ ORACLE 에 없는 config 비율: {missing} (매핑 신뢰 불가)"]
    return "\n".join(lines) + "\n"


def main():
    required, used_ratios, feature_only, missing = derive()
    if "--write" in sys.argv:
        OUT.write_text(render_md(required, used_ratios, feature_only, missing), encoding="utf-8")
        print(f"wrote {OUT}")
    print("ratios:", used_ratios)
    print("required accounts:", required)
    print("feature-only (not required):", feature_only)
    if missing:
        print("WARNING: config ratios not found in ORACLE:", missing)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
