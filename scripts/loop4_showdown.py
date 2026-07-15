#!/usr/bin/env python3
"""Loop 4 결판 조립 — 여섯 대조군 + 축별 기여(성장 ablation) + 부트스트랩(paired & firm-clustered).

★ dev만. holdout 미개봉. 동일 케이스셋·채점기·페널티·상수. 커밋된 대조군 scores.json 재사용, L4만 새 채점.
출력: JSON 요약(표준출력) — SHOWDOWN_L4.md 작성 근거.
firm-clustered 부트스트랩 = 검증방 Loop 3 권고(기업 내 상관 반영: 케이스가 아니라 corp 를 재표집).
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
import score as S                                        # noqa: E402
import run as SIM                                        # noqa: E402
from pit import as_of                                    # noqa: E402

RUNS = ROOT / "runs"
DIRS = {
    "시장중앙값(A)": "2026-07-15_loop1_market",
    "랜덤(B)": "2026-07-15_loop1_random",
    "baseline": "2026-07-15_loop1_baseline",
    "similarity_L2": "2026-07-15_loop2_similarity",
    "similarity_L3": "2026-07-15_loop3_similarity",
    "similarity_L4": "2026-07-15_loop4_similarity",
}
SEED = 20260715
B = 2000


def load_scores(name):
    p = RUNS / DIRS[name] / "scores.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def paired_ape(peers_path, tables, ratios, penalty, min_peers):
    peers = pd.read_parquet(peers_path)
    cases = S._cases_from_peers(peers, tables, ratios, penalty, min_peers)
    return pd.DataFrame(cases).set_index(["corp_code", "as_of", "ratio"])["ape"]


def boot_paired(ape_a, ape_b, rng):
    j = ape_a.index.intersection(ape_b.index)
    a, b = ape_a.loc[j].to_numpy(), ape_b.loc[j].to_numpy()
    n = len(j)
    diffs = np.array([np.median(b[idx]) - np.median(a[idx])
                      for idx in (rng.integers(0, n, n) for _ in range(B))])
    return {"n_pairs": int(n), "point_diff": round(float(np.median(b) - np.median(a)), 4),
            "ci95": [round(float(np.percentile(diffs, 2.5)), 4),
                     round(float(np.percentile(diffs, 97.5)), 4)],
            "significant": bool(np.percentile(diffs, 97.5) < 0)}


def boot_cluster(ape_a, ape_b, rng):
    """firm-clustered: corp 를 재표집(그 corp 의 모든 케이스 포함) → 기업 내 상관 반영."""
    j = ape_a.index.intersection(ape_b.index)
    a, b = ape_a.loc[j], ape_b.loc[j]
    corps = np.array(sorted({idx[0] for idx in j}))
    by_corp = {c: np.where(np.array([idx[0] for idx in j]) == c)[0] for c in corps}
    av, bv = a.to_numpy(), b.to_numpy()
    point = float(np.median(bv) - np.median(av))
    nC = len(corps)
    diffs = np.empty(B)
    for t in range(B):
        pick = corps[rng.integers(0, nC, nC)]
        idx = np.concatenate([by_corp[c] for c in pick])
        diffs[t] = np.median(bv[idx]) - np.median(av[idx])
    return {"n_corps": int(nC), "point_diff": round(point, 4),
            "ci95": [round(float(np.percentile(diffs, 2.5)), 4),
                     round(float(np.percentile(diffs, 97.5)), 4)],
            "significant": bool(np.percentile(diffs, 97.5) < 0)}


def growth_ablation(cfg, tables, ratios, penalty, min_peers, dev):
    """L4에서 성장 축만 껐을 때(재정규화) 점수 — 성장의 한계 기여."""
    wj = json.loads((RUNS / DIRS["similarity_L4"] / "weights.json").read_text(encoding="utf-8"))
    order, w = wj["order"], list(wj["weights"])
    if "growth" not in order:
        return None
    gi = order.index("growth")
    w_off = list(w); w_off[gi] = 0.0
    txt_idx, txt_mat = SIM.load_text_vectors()
    rows = []
    for y in dev:
        feats = as_of(f"{y}-05-15").features
        if not len(feats):
            continue
        pk = SIM.rank(feats, cfg, w_off, txt_idx, txt_mat, int(cfg["k"]))
        for tgt, plist in pk.items():
            for rr, p in enumerate(plist, 1):
                rows.append({"corp_code": tgt, "as_of": f"{y}-05-15", "rank": rr, "peer_code": p})
    off = pd.DataFrame(S._cases_from_peers(pd.DataFrame(rows), tables, ratios, penalty, min_peers))
    return {"growth_weight": w[gi], "ape_median_growth_off": round(float(off["ape"].median()), 4)}


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    tables, markets = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios),
                               float(cfg["penalty"]["quantile"]))
    min_peers = int(cfg["min_valid_peers"])

    table = {}
    for name in DIRS:
        j = load_scores(name)
        if not j:
            continue
        ov = j["overall"]
        table[name] = {"ape_median": ov["ape_median"], "within_10": ov.get("within_10pct"),
                       "within_20": ov.get("within_20pct"), "within_30": ov.get("within_30pct"),
                       "coverage": ov.get("coverage"),
                       "per_ratio": {r: j["per_ratio"][r]["ape_median"] for r in
                                     [x["name"] for x in ratios]}}
    wj = json.loads((RUNS / DIRS["similarity_L4"] / "weights.json").read_text(encoding="utf-8"))

    rng = np.random.default_rng(SEED)
    ape = {k: paired_ape(RUNS / DIRS[k] / "peers.parquet", tables, ratios, penalty, min_peers)
           for k in ("baseline", "similarity_L2", "similarity_L3", "similarity_L4")}
    boot = {
        "L4_vs_L3_paired": boot_paired(ape["similarity_L3"], ape["similarity_L4"], rng),
        "L4_vs_baseline_paired": boot_paired(ape["baseline"], ape["similarity_L4"], rng),
        "L4_vs_L3_clustered": boot_cluster(ape["similarity_L3"], ape["similarity_L4"], rng),
        "L4_vs_baseline_clustered": boot_cluster(ape["baseline"], ape["similarity_L4"], rng),
    }
    abl = growth_ablation(cfg, tables, ratios, penalty, min_peers, dev)

    l4 = table["similarity_L4"]["ape_median"]
    l3 = table["similarity_L3"]["ape_median"]
    base = table["baseline"]["ape_median"]
    out = {"table": table,
           "L4_weights": {"order": wj["order"], "weights": wj["weights"]},
           "active_axes": wj["order"], "segment_status": "데이터 없음(020 블록) — 제외",
           "growth_ablation": abl,
           "win_condition": 0.433, "win_met": bool(l4 <= 0.433),
           "L4_vs_L3_pct": round(100 * (l4 - l3) / l3, 2),
           "L4_vs_baseline_pct": round(100 * (l4 - base) / base, 2),
           "bootstrap": boot}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
