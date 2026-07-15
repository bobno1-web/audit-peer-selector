#!/usr/bin/env python3
"""게이트 측정값의 **독립 재집계** (LOOP_0I PART 2).

★ 측정 스크립트(gate_survivorship_v2 / gate_readjudicate)와 **별개 구현**이다.
   gate.py judge 가 이 모듈로 measured 를 원자료에서 스스로 재집계해 대조한다.
   측정값을 통제하는 자가 판정을 통제하지 못하게 한다(같은 버그 공유 금지).

또한 [비자명성](항진명제) 탐지에 쓰는 순수 함수들을 노출한다:
  입력 데이터를 바꿔도 값이 상수면 그 지표는 자명(항진명제)이다.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UNIV = ROOT / "data" / "pit" / "universe"
IND = ROOT / "data" / "pit" / "features" / "industry"
YEARS = list(range(2015, 2026))


# ---------- 원자료 로더 ----------
def load_universes():
    out = {}
    for y in YEARS:
        p = UNIV / f"universe_{y}.csv"
        if p.exists():
            with open(p, encoding="utf-8-sig") as f:
                out[y] = {r["corp_code"] for r in csv.DictReader(f)}
    return out


def load_induty2():
    """corp_code -> induty2. 전 연도 industry parquet 합집합(최근값)."""
    m = {}
    for y in YEARS:
        p = IND / f"industry_{y}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            for _, r in df.iterrows():
                code = (str(r.get("induty_code") or "")[:2]) or "NA"
                m[r["corp_code"]] = code
    return m


def load_delist_sample(cases_csv):
    with open(cases_csv, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r.get("kind") == "d1_delisted"]


# ---------- 독립 재집계 (measured 대조용) ----------
def recompute_missing_survivor(univ):
    """미제출-생존 평균%: T 이전 존재 & T 부재 & (T+1 or T+2) 존재. (D-2 독립 재구현.)"""
    per_T = {}
    for T in range(2017, 2024):
        before = set()
        for y in univ:
            if y < T:
                before |= univ[y]
        back = univ.get(T + 1, set()) | univ.get(T + 2, set())
        gaps = {c for c in before if c not in univ.get(T, set()) and c in back}
        per_T[T] = (len(gaps), len(univ.get(T, set())))
    pcts = [g / n * 100 for g, n in per_T.values() if n]
    return round(sum(pcts) / len(pcts), 2) if pcts else 0.0


def gap_corps(univ):
    out = set()
    for T in range(2017, 2024):
        before = set()
        for y in univ:
            if y < T:
                before |= univ[y]
        back = univ.get(T + 1, set()) | univ.get(T + 2, set())
        out |= {c for c in before if c not in univ.get(T, set()) and c in back}
    return out


def recompute_top1_concentration(univ, induty2):
    """미제출-생존 전체(표본 아님)의 최다 산업 점유%. 낮을수록 비쏠림."""
    gaps = gap_corps(univ)
    if not gaps:
        return 0.0
    dist = Counter(induty2.get(c, "NA") for c in gaps)
    return round(100 * dist.most_common(1)[0][1] / sum(dist.values()), 1)


def recompute_dead_retention(sample, univ):
    """★ 항진명제 지표: '실제 이탈'(2024·2025 연속 부재) ∩ '2025 잔존' — 정의상 공집합 → 항상 0."""
    u2024, u2025 = univ.get(2024, set()), univ.get(2025, set())
    departed = [r["corp_code"] for r in sample
                if r["corp_code"] not in u2024 and r["corp_code"] not in u2025]
    retained = [c for c in departed if c in u2025]
    return round(100 * len(retained) / len(departed), 2) if departed else 0.0


# ---------- judge 재집계 레지스트리 (metric recompute 이름 → 원자료에서 재집계) ----------
# ★ 원자료가 없으면 예외를 던져(판정 거부되게) 한다.
def _require(path):
    if not Path(path).exists():
        raise FileNotFoundError(str(path))


RECOMPUTE = {
    "missing_survivor": lambda: (_require(UNIV) or recompute_missing_survivor(load_universes())),
    "concentration": lambda: (_require(UNIV) or _require(IND)
                              or recompute_top1_concentration(load_universes(), load_induty2())),
}


# ---------- [비자명성] 항진명제 탐지 ----------
def is_tautological(recompute_fn, perturbed_inputs):
    """입력을 여러 번 교란해 재집계했을 때 값이 상수면 자명(항진명제)."""
    vals = {recompute_fn(inp) for inp in perturbed_inputs}
    return len(vals) == 1


def _cli():
    import sys
    univ = load_universes()
    ind = load_induty2()
    ms = recompute_missing_survivor(univ)
    tc = recompute_top1_concentration(univ, ind)
    sample = load_delist_sample(ROOT / "runs" / "2026-07-15_gate_survivorship" / "cases.csv")
    dr = recompute_dead_retention(sample, univ)
    print(json.dumps({"missing_survivor_pct": ms, "top1_concentration_pct": tc,
                      "dead_retention_pct": dr, "n_gaps": len(gap_corps(univ)),
                      "n_delist_sample": len(sample)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
