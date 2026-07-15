#!/usr/bin/env python3
"""Loop 3 가중치 탐색 + similarity(4축) 최종 채점.

★ Loop 2(loop2_search)와 **동일한 학습 절차** — dev 격자 탐색(holdout 미사용), 시점별 타겟 표본으로
  성분 유사도 precompute 후 각 가중치 조합을 조합·랭킹·채점. 유일한 차이는 성분 수(3→4: 시총·섹션텍스트).
best 가중치 → runs/…loop3_similarity/weights.json → 전량 재실행 + 채점(baseline·L2와 동일 채점기·페널티·상수).
"""
import itertools
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
from pit import as_of                                    # noqa: E402
import score as S                                        # noqa: E402
import run as SIM                                        # noqa: E402

SEED = 20260715                                          # Loop 2와 동일 표본 시드(절차 불변)
SUB = 250                                                # 탐색용 시점별 타겟 표본(Loop 2와 동일)
RUN = ROOT / "runs" / "2026-07-15_loop3_similarity"


def component_vectors(feats, cfg, txt_idx, txt_mat, sub_idx):
    comps = list(cfg["similarity"]["components"])
    A = SIM.year_arrays(feats, cfg, txt_idx, txt_mat)
    codes = A["codes"]
    C = {c: [] for c in comps}
    for i in sub_idx:
        for c in comps:
            C[c].append(SIM.SIMS[c](A, i))
    return codes, {c: np.array(C[c]) for c in comps}, list(sub_idx)


def peers_from_combo(data, comps, w, k):
    w = np.array(w, float)
    w = w / w.sum()
    rows = []
    for T, (codes, C, subidx) in data.items():
        total = sum(w[c] * C[comp] for c, comp in enumerate(comps))
        for r, i in enumerate(subidx):
            total[r, i] = -np.inf
            order = np.argsort(total[r])[::-1][:k]
            for rank_, j in enumerate(order, 1):
                rows.append({"corp_code": codes[i], "as_of": T, "rank": rank_, "peer_code": codes[j]})
    return pd.DataFrame(rows)


def main():
    cfg = S.load_cfg()
    ratios, k = cfg["ratios"], int(cfg["k"])
    within, min_peers = cfg["within"], int(cfg["min_valid_peers"])
    q = float(cfg["penalty"]["quantile"])
    comps = list(cfg["similarity"]["components"])
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    tables, markets = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios), q)
    print(f"penalty={penalty:.4f} (baseline·L2와 동일 자); components={comps}", file=sys.stderr)

    txt_idx, txt_mat = SIM.load_text_vectors()
    print(f"section text vectors: {'없음' if txt_mat is None else txt_mat.shape}", file=sys.stderr)

    data = {}
    rnd = random.Random(SEED)
    for y in dev:
        T = f"{y}-05-15"
        feats = as_of(T).features
        n = len(feats)
        sub = sorted(rnd.sample(range(n), min(SUB, n)))
        data[T] = component_vectors(feats, cfg, txt_idx, txt_mat, sub)

    grid = cfg["similarity"]["weight_grid"]
    combos = {tuple(np.round(np.array(w) / sum(w), 4))
              for w in itertools.product(grid, repeat=len(comps)) if sum(w) > 0}
    best, best_ape = None, 1e9
    for w in sorted(combos):
        pdf = peers_from_combo(data, comps, w, k)
        cases = S._cases_from_peers(pdf, tables, ratios, penalty, min_peers)
        ape = float(pd.DataFrame(cases)["ape"].median())
        if ape < best_ape:
            best, best_ape = list(w), ape
    print(f"best weights {comps}={best}  dev표본 APE중앙값={best_ape:.4f} "
          f"(combos={len(combos)})", file=sys.stderr)

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "weights.json").write_text(json.dumps(
        {"weights": best, "order": comps, "search": "dev grid, holdout 미사용",
         "subsample_APE_median": round(best_ape, 4), "grid": grid, "n_combos": len(combos)},
        ensure_ascii=False, indent=2), encoding="utf-8")

    full = SIM.run(dev, best, RUN, guard=True)
    cases = S._cases_from_peers(full, tables, ratios, penalty, min_peers)
    agg = S.aggregate(cases, ratios, within)
    dist, _ = S.ratio_count_distribution(tables, ratios)
    obj = {"run_id": RUN.name, "engine": "similarity_l3",
           "as_of": [f"{y}-05-15" for y in dev], "k": k, "weights": best, "components": comps,
           "ratios": [r["name"] for r in ratios], "split": "dev",
           "n_cases_total": agg["n_cases"], "overall": agg["overall"], "per_ratio": agg["per_ratio"],
           "params": {"penalty_ape": round(penalty, 4)}, "ratio_count_distribution_pct": dist}
    (RUN / "scores.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"weights": best, "components": comps, "overall": agg["overall"],
                      "per_ratio": {r: agg["per_ratio"][r]["ape_median"] for r in
                                    [x["name"] for x in ratios]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
