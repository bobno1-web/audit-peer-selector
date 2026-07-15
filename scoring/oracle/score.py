#!/usr/bin/env python3
"""채점기 — ORACLE.md 를 코드로 (Loop 1).

입력: peers.parquet (엔진 출력 파일만). ★ engines/ 를 import하지 않는다.
      data/pit/targets/ 는 여기서만 읽는다(as_of(T, with_targets=True)).
절차: 각 (타겟 i, 시점 T)에서 그 타겟에 '정의된' 비율만 채점.
  정의됨 = 분자·분모 계정 존재 + 분모>0. peer k의 해당 비율 중앙값 → 예측.
  APE = |예측 - 실제| / |실제|. 유효 peer < min_valid_peers → FAIL → 페널티(제외 아님).
페널티는 dev 의 '시장중앙값'(대조군A) APE 분포 상위 분위수에서 유도(임의상수 아님).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pit import as_of                                    # noqa: E402

CONFIG = ROOT / "config" / "default.yaml"


def load_cfg():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def ratio_tables(dev_years, ratios):
    """{T: DataFrame(index=corp_code, 각 비율값 또는 NaN)}, {T: {비율: 시장중앙값}}."""
    tables, markets = {}, {}
    for y in dev_years:
        T = f"{y}-05-15"
        tg = as_of(T, with_targets=True).targets           # ★ 채점기만 targets 접근
        if not len(tg):
            continue
        tg = tg.set_index("corp_code")
        rt = pd.DataFrame(index=tg.index)
        for r in ratios:
            num = pd.to_numeric(tg[r["numerator"]], errors="coerce")
            den = pd.to_numeric(tg[r["denominator"]], errors="coerce")
            rt[r["name"]] = (num / den).where(den > 0)     # 분모<=0/결측 → 정의 안 됨(NaN)
        tables[T] = rt
        markets[T] = {r["name"]: rt[r["name"]].median(skipna=True) for r in ratios}
    return tables, markets


def _cases_from_peers(peers_df, tables, ratios, penalty, min_peers):
    cases = []
    grp = peers_df.groupby(["as_of", "corp_code"])["peer_code"].apply(list)
    for (T, corp), plist in grp.items():
        rt = tables.get(T)
        if rt is None or corp not in rt.index:
            continue
        for r in ratios:
            actual = rt.at[corp, r["name"]]
            if pd.isna(actual) or actual == 0:             # 타겟에 정의 안 됨 → 채점 제외
                continue
            pv = [rt.at[p, r["name"]] for p in plist
                  if p in rt.index and not pd.isna(rt.at[p, r["name"]])]
            if len(pv) >= min_peers:
                ape, fail = abs(np.median(pv) - actual) / abs(actual), False
            else:
                ape, fail = penalty, True                  # FAIL = 제외 아닌 페널티
            cases.append({"corp_code": corp, "as_of": T, "ratio": r["name"],
                          "ape": float(ape), "fail": fail})
    return cases


def _cases_from_market(tables, markets, ratios):
    """대조군 A: peer 선정 없이 시장중앙값을 예측치로. (페널티 유도 소스이기도.)"""
    cases = []
    for T, rt in tables.items():
        for r in ratios:
            mm = markets[T][r["name"]]
            if pd.isna(mm):
                continue
            col = rt[r["name"]]
            for corp, actual in col.items():
                if pd.isna(actual) or actual == 0:
                    continue
                cases.append({"corp_code": corp, "as_of": T, "ratio": r["name"],
                              "ape": float(abs(mm - actual) / abs(actual)), "fail": False})
    return cases


def ratio_count_distribution(tables, ratios):
    dist = {}
    total = 0
    for rt in tables.values():
        cnt = rt[[r["name"] for r in ratios]].notna().sum(axis=1)
        for c in cnt:
            dist[int(c)] = dist.get(int(c), 0) + 1
            total += 1
    return {k: round(100 * v / total, 1) for k, v in sorted(dist.items())}, total


def aggregate(cases, ratios, within):
    df = pd.DataFrame(cases)
    return {
        "n_cases": len(df),
        "overall": {"ape_median": round(float(df["ape"].median()), 4),
                    **{f"within_{w}pct": round(float((df["ape"] <= w / 100).mean()), 4)
                       for w in within},
                    "coverage": round(float((~df["fail"]).mean()), 4)},
        "per_ratio": {r["name"]: {
            "ape_median": round(float(df[df.ratio == r["name"]]["ape"].median()), 4),
            "n": int((df.ratio == r["name"]).sum())} for r in ratios},
    }


def derive_penalty(market_cases, quantile):
    """FAIL 페널티 = 대조군A(시장중앙값) APE 분포의 상위 분위수(config). dev에서 유도."""
    apes = np.array([c["ape"] for c in market_cases], dtype=float)
    return float(np.quantile(apes, quantile))
