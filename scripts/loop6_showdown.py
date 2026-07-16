#!/usr/bin/env python3
"""Loop 6 결판 — 일곱+ 대조군, 전체/안정 APE 둘 다, firm-clustered 부트스트랩. dev 전용.

★ 모든 대조군을 **교정 targets**(PART0 매출채권 버그교정)로 재채점 → PART0 효과 격리.
★ 컨트롤은 ORACLE 동결 예측(median@k5), L6 = L4선정 + median@k10(B) + 예측불가분리(C).
★ B 효과 = L4선정 @k5→@k7→@k10(교정 targets, coverage 분해). holdout 미개봉.
출력: JSON(표준출력) — SHOWDOWN_L6.md 근거.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
import score as S                                           # noqa: E402
from pit import as_of                                       # noqa: E402
import loop6_predict as LP                                  # noqa: E402

RUNS = ROOT / "runs"
RUN = RUNS / "2026-07-16_loop6"
# 컨트롤 peers.parquet(선정) — 교정 targets 로 재채점(median@k5)
CTRL = {
    "baseline": "2026-07-15_loop1_baseline",
    "similarity_L2": "2026-07-15_loop2_similarity",
    "similarity_L3": "2026-07-15_loop3_similarity",
    "similarity_L4": "2026-07-15_loop4_similarity",
    "similarity_L5": "2026-07-16_loop5_similarity",
    "랜덤(B)": "2026-07-15_loop1_random",
}
SEED = 20260715
NB = 2000


def to_series(cases):
    return pd.DataFrame(cases).set_index(["corp_code", "as_of", "ratio"])["ape"]


def boot_paired(a, b, rng):
    j = a.index.intersection(b.index)
    av, bv = a.loc[j].to_numpy(), b.loc[j].to_numpy()
    n = len(j)
    diffs = np.array([np.median(bv[idx]) - np.median(av[idx])
                      for idx in (rng.integers(0, n, n) for _ in range(NB))])
    return {"n_pairs": int(n), "point_diff": round(float(np.median(bv) - np.median(av)), 4),
            "ci95": [round(float(np.percentile(diffs, 2.5)), 4),
                     round(float(np.percentile(diffs, 97.5)), 4)],
            "significant": bool(np.percentile(diffs, 97.5) < 0)}


def boot_cluster(a, b, rng):
    j = a.index.intersection(b.index)
    av, bv = a.loc[j].to_numpy(), b.loc[j].to_numpy()
    corps = np.array([idx[0] for idx in j])
    uniq = np.array(sorted(set(corps)))
    by = {c: np.where(corps == c)[0] for c in uniq}
    nC = len(uniq)
    diffs = np.empty(NB)
    for t in range(NB):
        pick = uniq[rng.integers(0, nC, nC)]
        idx = np.concatenate([by[c] for c in pick])
        diffs[t] = np.median(bv[idx]) - np.median(av[idx])
    return {"n_corps": int(nC), "point_diff": round(float(np.median(bv) - np.median(av)), 4),
            "ci95": [round(float(np.percentile(diffs, 2.5)), 4),
                     round(float(np.percentile(diffs, 97.5)), 4)],
            "significant": bool(np.percentile(diffs, 97.5) < 0)}


def cov_of(cases):
    return round(float(np.mean([not c["fail"] for c in cases])), 4) if cases else 0.0


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    rnames = [r["name"] for r in ratios]
    min_peers = int(cfg["min_valid_peers"])
    K5 = int(cfg["k"])
    KL6 = int(cfg["prediction"]["k"])                       # L6 예측 k (=10)
    q_sep = float(cfg["separation"]["numerator_over_assets_quantile"])
    ys, Ts = LP.dev_Ts(cfg)
    tables, markets = S.ratio_tables(ys, ratios)            # ★ 교정 targets(라이브)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios),
                               float(cfg["penalty"]["quantile"]))

    # 분리 플래그(교정 targets 재무구조)
    flag, tau, s_counts = LP.separation(Ts, ratios, q_sep)

    # L4 선정 peer(top-max) + 유사도 — L6/B분해 공용
    kmax = max(cfg["prediction"]["k_grid"] + [K5, KL6])
    peers_sim = LP.l4_peers_with_sim(cfg, Ts, kmax)
    mism = LP.verify_selection(peers_sim, K5)

    def per_ratio_med(cases):
        return {r: round(float(np.median([c["ape"] for c in cases if c["ratio"] == r])), 4)
                for r in rnames}

    rows = {}       # name -> cases
    # 컨트롤(교정 targets, median@k5)
    rows["시장중앙값(A)"] = S._cases_from_market(tables, markets, ratios)
    for name, d in CTRL.items():
        p = RUNS / d / "peers.parquet"
        if p.exists():
            rows[name] = S._cases_from_peers(pd.read_parquet(p), tables, ratios, penalty, min_peers)
    # L6 = L4선정 + median@k10
    rows["L6(L4+median@k10)"] = LP.cases_predict(peers_sim, tables, ratios, penalty,
                                                 min_peers, LP.AGG["median"], KL6)

    table = {}
    for name, cases in rows.items():
        sr = LP.split_report(cases, flag)
        table[name] = {"ape_median_overall": round(sr["overall_median"], 4),
                       "ape_median_stable": round(sr["stable_median"], 4),
                       "excl_rate": sr["excl_rate"], "coverage": cov_of(cases),
                       "per_ratio_overall": per_ratio_med(cases)}

    # B 분해: L4선정 median @ k5/k7/k10 (교정 targets) + coverage
    b_decomp = {}
    for kk in cfg["prediction"]["k_grid"]:
        c = LP.cases_predict(peers_sim, tables, ratios, penalty, min_peers, LP.AGG["median"], kk)
        b_decomp[f"median@k{kk}"] = {"overall": round(LP.median_ape(c), 4),
                                     "stable": round(LP.split_report(c, flag)["stable_median"], 4),
                                     "coverage": cov_of(c)}
    # 대안 집계 함수 @k10 (참고)
    alt = {}
    for m in cfg["prediction"]["methods_grid"]:
        c = LP.cases_predict(peers_sim, tables, ratios, penalty, min_peers, LP.AGG[m], KL6)
        alt[f"{m}@k{KL6}"] = round(LP.median_ape(c), 4)

    # 부트스트랩(전체 & 안정): L6 vs L4(교정@k5), L6 vs baseline(교정)
    l4c = LP.cases_predict(peers_sim, tables, ratios, penalty, min_peers, LP.AGG["median"], K5)
    l6c = rows["L6(L4+median@k10)"]
    basec = rows["baseline"]
    rng = np.random.default_rng(SEED)
    sA_l6, sA_l4, sA_base = to_series(l6c), to_series(l4c), to_series(basec)
    # 안정 subset series
    def stable_series(cases):
        s = to_series(cases)
        keep = [idx for idx in s.index if idx not in flag]
        return s.loc[keep]
    boot = {
        "L6_vs_L4_paired_overall": boot_paired(sA_l4, sA_l6, rng),
        "L6_vs_L4_clustered_overall": boot_cluster(sA_l4, sA_l6, rng),
        "L6_vs_baseline_paired_overall": boot_paired(sA_base, sA_l6, rng),
        "L6_vs_baseline_clustered_overall": boot_cluster(sA_base, sA_l6, rng),
        "L6_vs_L4_paired_stable": boot_paired(stable_series(l4c), stable_series(l6c), rng),
        "L6_vs_L4_clustered_stable": boot_cluster(stable_series(l4c), stable_series(l6c), rng),
    }

    l6o = table["L6(L4+median@k10)"]["ape_median_overall"]
    l6s = table["L6(L4+median@k10)"]["ape_median_stable"]
    l4o = table["similarity_L4"]["ape_median_overall"]
    baseo = table["baseline"]["ape_median_overall"]
    out = {
        "targets": "corrected(PART0 receivable fix)", "dev_years": ys, "penalty": round(penalty, 4),
        "selection_mismatch_vs_committed_L4_k5": mism,
        "separation": {"q_sep": q_sep, "tau_by_ratio": {k: round(v, 6) for k, v in tau.items()},
                       "n_flagged": len(flag), "defined_by_ratio": s_counts},
        "table": table,
        "B_k_decomposition": b_decomp, "alt_aggregators_k10": alt,
        "win_condition": 0.433,
        "win_met_overall": bool(l6o <= 0.433), "win_met_stable": bool(l6s <= 0.433),
        "L6_vs_L4_overall_pct": round(100 * (l6o - l4o) / l4o, 2),
        "L6_vs_baseline_overall_pct": round(100 * (l6o - baseo) / baseo, 2),
        "bootstrap": boot,
    }
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "showdown_l6.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
