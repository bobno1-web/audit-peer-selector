#!/usr/bin/env python3
"""Loop 2 가중치 탐색 + similarity 최종 채점.

★ 동결(SUPERSEDED): engines/similarity/run.py 는 Loop 3에서 4축(시총·섹션텍스트)으로 진화했다.
  이 드라이버는 L2-시대(3축·전문TF-IDF) 엔진에 묶여 있으며, L2 결과는
  runs/2026-07-15_loop2_similarity/scores.json(커밋됨)에 보존된다. L2 재현은 그 커밋에서.
  현행 학습은 scripts/loop3_search.py 다. (이 파일은 진화한 엔진과 호환되지 않을 수 있다.)


dev 에서 (산업·규모·텍스트) 가중치를 격자 탐색(홀드아웃 미사용). 속도를 위해 시점별 타겟
표본으로 component 유사도를 한 번 precompute 후 각 가중치 조합을 조합·랭킹·채점.
best 가중치 → runs/…similarity/weights.json → 전량 재실행 + 채점(baseline과 동일 채점기·페널티·상수).
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

SEED = 20260715
SUB = 250                                                # 탐색용 시점별 타겟 표본
RUN = ROOT / "runs" / "2026-07-15_loop2_similarity"


def component_vectors(feats, cfg, txt_idx, txt_mat, sub_idx):
    codes, induty, keys, prefixes, logs, tmat = SIM.year_arrays(feats, cfg, txt_idx, txt_mat)
    n = len(codes)
    IND, SCA, TXT = [], [], []
    for i in sub_idx:
        tier = np.full(n, len(prefixes), dtype=float)
        for ti, p in reversed(list(enumerate(prefixes))):
            tier = np.where((keys[p] == keys[p][i]) & (induty != ""), ti, tier)
        IND.append(np.where(tier < len(prefixes), 1.0 - tier / len(prefixes), 0.0))
        d2 = np.zeros(n)
        for lg in logs:
            d2 = d2 + (lg - lg[i]) ** 2
        s = np.exp(-np.sqrt(d2))
        SCA.append(np.where(np.isnan(s), 0.0, s))
        TXT.append(tmat @ tmat[i] if tmat.shape[1] else np.zeros(n))
    return codes, np.array(IND), np.array(SCA), np.array(TXT), [codes[i] for i in sub_idx], list(sub_idx)


def peers_from_combo(comps, w, k):
    rows = []
    w = np.array(w, float)
    w = w / w.sum()
    for T, (codes, IND, SCA, TXT, subcodes, subidx) in comps.items():
        total = w[0] * IND + w[1] * SCA + w[2] * TXT
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
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    tables, markets = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios), q)
    print(f"penalty={penalty:.4f} (baseline과 동일 자)", file=sys.stderr)

    txt_idx, txt_mat = SIM.load_text_vectors()
    print(f"text vectors: {'없음' if txt_mat is None else txt_mat.shape}", file=sys.stderr)

    comps = {}
    rnd = random.Random(SEED)
    for y in dev:
        T = f"{y}-05-15"
        feats = as_of(T).features
        n = len(feats)
        sub = sorted(rnd.sample(range(n), min(SUB, n)))
        comps[T] = component_vectors(feats, cfg, txt_idx, txt_mat, sub)

    grid = cfg["similarity"]["weight_grid"]
    combos = {tuple(np.round(np.array(w) / sum(w), 4)) for w in itertools.product(grid, repeat=3)
              if sum(w) > 0}
    best, best_ape = None, 1e9
    for w in sorted(combos):
        pdf = peers_from_combo(comps, w, k)
        cases = S._cases_from_peers(pdf, tables, ratios, penalty, min_peers)
        ape = float(pd.DataFrame(cases)["ape"].median())
        if ape < best_ape:
            best, best_ape = list(w), ape
    print(f"best weights (산업,규모,텍스트)={best}  dev표본 APE중앙값={best_ape:.4f}", file=sys.stderr)

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "weights.json").write_text(json.dumps(
        {"weights": best, "order": ["industry", "scale", "text"],
         "search": "dev grid, holdout 미사용", "subsample_APE_median": round(best_ape, 4),
         "grid": grid}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 전량 재실행 + 채점 (baseline과 동일 케이스셋·채점기·페널티)
    full = SIM.run(dev, best, RUN, guard=True)
    cases = S._cases_from_peers(full, tables, ratios, penalty, min_peers)
    agg = S.aggregate(cases, ratios, within)
    dist, _ = S.ratio_count_distribution(tables, ratios)
    obj = {"run_id": RUN.name, "engine": "similarity",
           "as_of": [f"{y}-05-15" for y in dev], "k": k, "weights": best,
           "ratios": [r["name"] for r in ratios], "split": "dev",
           "n_cases_total": agg["n_cases"], "overall": agg["overall"], "per_ratio": agg["per_ratio"],
           "params": {"penalty_ape": round(penalty, 4)}, "ratio_count_distribution_pct": dist}
    (RUN / "scores.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"weights": best, "overall": agg["overall"],
                      "per_ratio": {r: agg["per_ratio"][r]["ape_median"] for r in
                                    [x["name"] for x in ratios]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
