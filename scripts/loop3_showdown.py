#!/usr/bin/env python3
"""Loop 3 결판 조립 — 다섯 대조군 + 텍스트 가중치 판정 + 시총 중복 + 부트스트랩 유의성.

★ dev만. holdout 미개봉. 동일 케이스셋·채점기·페널티·상수. 커밋된 대조군 scores.json 을 재사용
  (Loop 2가 Loop 1 대조군을 재사용한 방식과 동일). L3 만 새로 채점.
출력: JSON 요약(표준출력) — SHOWDOWN_L3.md 작성 근거. peers.parquet 로 paired 부트스트랩.
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
import score as S                                        # noqa: E402

RUNS = ROOT / "runs"
DIRS = {
    "시장중앙값(A)": "2026-07-15_loop1_market",
    "랜덤(B)": "2026-07-15_loop1_random",
    "baseline": "2026-07-15_loop1_baseline",
    "similarity_L2": "2026-07-15_loop2_similarity",
    "similarity_L3": "2026-07-15_loop3_similarity",
}
SEED = 20260715
B = 2000                                                 # 부트스트랩 반복


def load_scores(name):
    p = RUNS / DIRS[name] / "scores.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def paired_cases(peers_path, tables, ratios, penalty, min_peers):
    peers = pd.read_parquet(peers_path)
    cases = S._cases_from_peers(peers, tables, ratios, penalty, min_peers)
    df = pd.DataFrame(cases).set_index(["corp_code", "as_of", "ratio"])["ape"]
    return df


def bootstrap_median_diff(ape_a, ape_b, rng):
    """paired: median(b) - median(a). 음수=b가 개선. 95% CI."""
    j = ape_a.index.intersection(ape_b.index)
    a = ape_a.loc[j].to_numpy()
    b = ape_b.loc[j].to_numpy()
    n = len(j)
    point = float(np.median(b) - np.median(a))
    diffs = np.empty(B)
    for i in range(B):
        idx = rng.integers(0, n, n)
        diffs[i] = np.median(b[idx]) - np.median(a[idx])
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    return {"n_pairs": int(n), "point_diff": round(point, 4),
            "ci95": [round(lo, 4), round(hi, 4)], "significant": bool(hi < 0)}


def mktcap_scale_corr():
    import yaml
    cfg = yaml.safe_load((ROOT / "config/default.yaml").read_text(encoding="utf-8"))
    sf = cfg["similarity"]["scale_features"]
    cm, ca = [], []
    for y in range(2016, 2023):
        sc = pd.read_parquet(ROOT / f"data/pit/features/scale/scale_{y}.parquet")
        mk = pd.read_parquet(ROOT / f"data/pit/features/mktcap/mktcap_{y}.parquet")
        m = sc.merge(mk[["corp_code", "시가총액"]], on="corp_code", how="inner")
        for c in sf + ["시가총액"]:
            m[c] = pd.to_numeric(m[c], errors="coerce")
        lg = np.log(m[sf + ["시가총액"]].where(lambda x: x > 0)).dropna()
        cm.append(np.corrcoef(lg["시가총액"], lg[sf[0]])[0, 1])
        ca.append(np.corrcoef(lg["시가총액"], lg[sf[1]])[0, 1])
    return {"corr_log_시총_매출": round(float(np.mean(cm)), 3),
            "corr_log_시총_자산": round(float(np.mean(ca)), 3)}


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
    wj = json.loads((RUNS / DIRS["similarity_L3"] / "weights.json").read_text(encoding="utf-8"))

    rng = np.random.default_rng(SEED)
    ape = {k: paired_cases(RUNS / DIRS[k] / "peers.parquet", tables, ratios, penalty, min_peers)
           for k in ("baseline", "similarity_L2", "similarity_L3")}
    boot = {"L3_vs_baseline": bootstrap_median_diff(ape["baseline"], ape["similarity_L3"], rng),
            "L3_vs_L2": bootstrap_median_diff(ape["similarity_L2"], ape["similarity_L3"], rng)}

    base = table["baseline"]["ape_median"]
    l3 = table["similarity_L3"]["ape_median"]
    out = {"table": table,
           "L3_weights": {"order": wj["order"], "weights": wj["weights"]},
           "text_weight_nonzero": bool(wj["weights"][wj["order"].index("text")] > 0),
           "mktcap_weight": wj["weights"][wj["order"].index("mktcap")],
           "mktcap_scale_corr": mktcap_scale_corr(),
           "win_condition": 0.433, "win_met": bool(l3 <= 0.433),
           "L3_vs_baseline_pct": round(100 * (l3 - base) / base, 1),
           "bootstrap": boot}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
