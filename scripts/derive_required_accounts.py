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


def derive_by_ratio():
    """★ 비율별 필요 계정(합집합 아님). 기업 단위 '필수 계정' 개념은 없다(Loop 0-G C-2).
    반환: (per_ratio[{name, accounts:[num,den]}], allowed, missing_in_oracle)."""
    oracle_text = ORACLE.read_text(encoding="utf-8")
    ratios, allowed = load_config(CONFIG)
    per_ratio, missing = [], []
    for r in ratios:
        name = r.get("name")
        if not name:
            continue
        if name not in oracle_text:            # ORACLE 이 권위. 없으면 매핑 불신.
            missing.append(name)
            continue
        accts = [r[k] for k in ("numerator", "denominator") if r.get(k)]
        per_ratio.append({"name": name, "accounts": accts})
    return per_ratio, allowed, missing


def fetch_accounts():
    """데이터 '수집' 대상 계정 집합(비율 계정 합집합). ★ '기업 단위 필수'가 아니라 수집용.
    각 기업에서 어떤 비율이 정의되는지는 defined_ratios() 가 재무구조로 판정한다."""
    per_ratio, _, _ = derive_by_ratio()
    return sorted({a for r in per_ratio for a in r["accounts"]})


def defined_ratios(financials, per_ratio=None):
    """타겟에서 '정의된' 비율 이름 집합. 정의됨 = 분자·분모 계정이 존재(not None)하고 분모>0.
    ★ 입력은 타겟의 재무구조뿐이다. 엔진 입력이 없으므로 엔진이 이 집합에 관여할 수 없다."""
    if per_ratio is None:
        per_ratio, _, _ = derive_by_ratio()
    out = set()
    for r in per_ratio:
        accts = r["accounts"]
        num = financials.get(accts[0]) if accts else None
        den = financials.get(accts[1]) if len(accts) > 1 else None
        if num is not None and den is not None and den > 0:
            out.add(r["name"])
    return out


def derive():
    """하위호환: (수집대상 계정, 비율명 목록, 피처전용, ORACLE부재비율).
    [0]은 '수집 대상'(합집합)이지 '기업 단위 필수'가 아니다 — derive_by_ratio 가 본체."""
    per_ratio, allowed, missing = derive_by_ratio()
    required = fetch_accounts()
    feature_only = [a for a in allowed if a not in required]
    return required, [r["name"] for r in per_ratio], feature_only, missing


def render_md():
    per_ratio, allowed, missing = derive_by_ratio()
    feature_only = [a for a in allowed if a not in fetch_accounts()]
    lines = [
        "# REQUIRED_ACCOUNTS — 비율별 필요 계정 (자동 유도)",
        "",
        "> ★ 이 파일은 `scripts/derive_required_accounts.py` 의 **산출물**이다. **손으로 편집 금지.**",
        "> 갱신: `python scripts/derive_required_accounts.py --write`.",
        "",
        "유도 경로: `docs/ORACLE.md` 채점 비율 → `config/default.yaml` 비율→계정 매핑.",
        "",
        "## ★ 기업 단위 '필수 계정' = 없음",
        "필수는 **비율 단위로만** 정의된다. 한 기업에서 어떤 비율이 채점되는지는 그 기업의 재무구조가",
        "정한다(분자·분모 존재 + 분모>0). '6계정 전부 확보' 같은 전-계정 필수 조건은 오라클에 없다",
        "(Loop 0-D 종업원수·0-F 6계정전부와 같은 발명된 요건이었다 — `DECISIONS` D-013).",
        "",
        f"## 비율별 필요 계정 ({len(per_ratio)}개 비율)",
        "".join(f"\n- **{r['name']}**: {' , '.join(r['accounts'])}" for r in per_ratio),
        "",
        f"## 데이터 수집 대상 계정 (비율 계정 합집합, {len(fetch_accounts())}개) — '필수'가 아니라 '수집'",
        "".join(f"\n- {a}" for a in fetch_accounts()),
        "",
        "## 피처 전용 — 엔진 허용 입력 중 채점 비율에 안 쓰이는 것",
        "  없다고 그 기업을 버리지 않는다. (config `engine_allowed_inputs` 에서 자동 계산)",
        "".join(f"\n- {a}" for a in feature_only),
    ]
    if missing:
        lines += ["", f"## ⚠ ORACLE 에 없는 config 비율: {missing} (매핑 신뢰 불가)"]
    return "\n".join(lines) + "\n"


def main():
    per_ratio, _, missing = derive_by_ratio()
    if "--write" in sys.argv:
        OUT.write_text(render_md(), encoding="utf-8")
        print(f"wrote {OUT}")
    print("per-ratio accounts:")
    for r in per_ratio:
        print(f"  {r['name']}: {r['accounts']}")
    print("collection set (union, not per-company required):", fetch_accounts())
    if missing:
        print("WARNING: config ratios not found in ORACLE:", missing)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
