#!/usr/bin/env python3
"""Loop 1 채점 드라이버 — 세 대조군을 나란히 채점 (dev만, holdout 안 엶).

(A) 시장중앙값 (peer 선정 없음)  (B) 랜덤 5 peer  (C) baseline (산업+규모).
페널티는 dev 의 (A) APE 분포 상위 분위수(config)에서 유도 → 세 엔진에 동일 적용(고정 자).
각 run 의 scores.json + docs/BASELINE_SCORE.md 작성.
"""
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
from pit import as_of                                    # noqa: E402
import score as S                                        # noqa: E402

SEED = 20260715


def dev_years_with_data(cfg):
    dev = cfg["pit_split"]["dev_years"]
    sd = ROOT / "data" / "pit" / "features" / "scale"
    return [y for y in dev if (sd / f"scale_{y}.parquet").exists()]


def make_random_peers(dev_years, k):
    rows = []
    for y in dev_years:
        T = f"{y}-05-15"
        codes = list(as_of(T).features["corp_code"])
        rnd = random.Random(f"{SEED}-{y}")
        for target in codes:
            pool = [c for c in codes if c != target]
            for rank, p in enumerate(rnd.sample(pool, min(k, len(pool))), 1):
                rows.append({"corp_code": target, "as_of": T, "rank": rank, "peer_code": p})
    return pd.DataFrame(rows)


def write_scores(run_dir, engine, agg, dev_years, ratios, k, within, penalty, dist):
    run_dir.mkdir(parents=True, exist_ok=True)
    obj = {"run_id": run_dir.name, "engine": engine,
           "as_of": [f"{y}-05-15" for y in dev_years], "k": k,
           "ratios": [r["name"] for r in ratios], "split": "dev",
           "n_cases_total": agg["n_cases"], "overall": agg["overall"],
           "per_ratio": agg["per_ratio"],
           "params": {"penalty_ape": round(penalty, 4), "penalty_from": "dev control-A upper tail"},
           "ratio_count_distribution_pct": dist}
    (run_dir / "scores.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return obj


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    k = int(cfg["k"])
    within = cfg["within"]
    min_peers = int(cfg["min_valid_peers"])
    q = float(cfg["penalty"]["quantile"])
    dev = dev_years_with_data(cfg)
    print("dev years:", dev, file=sys.stderr)

    tables, markets = S.ratio_tables(dev, ratios)
    dist, _ = S.ratio_count_distribution(tables, ratios)

    # 대조군 A(시장중앙값) → 페널티 유도
    market_cases = S._cases_from_market(tables, markets, ratios)
    penalty = S.derive_penalty(market_cases, q)
    print(f"penalty(APE, dev A 분포 q{q}) = {penalty:.4f}", file=sys.stderr)

    baseline = pd.read_parquet(ROOT / "runs" / "2026-07-15_loop1_baseline" / "peers.parquet")
    rand_dir = ROOT / "runs" / "2026-07-15_loop1_random"
    rand_dir.mkdir(parents=True, exist_ok=True)
    rnd_peers = make_random_peers(dev, k)
    rnd_peers.to_parquet(rand_dir / "peers.parquet", index=False)

    base_cases = S._cases_from_peers(baseline, tables, ratios, penalty, min_peers)
    rand_cases = S._cases_from_peers(rnd_peers, tables, ratios, penalty, min_peers)

    a = write_scores(ROOT / "runs" / "2026-07-15_loop1_market", "control_A_market",
                     S.aggregate(market_cases, ratios, within), dev, ratios, k, within, penalty, dist)
    b = write_scores(rand_dir, "control_B_random",
                     S.aggregate(rand_cases, ratios, within), dev, ratios, k, within, penalty, dist)
    c = write_scores(ROOT / "runs" / "2026-07-15_loop1_baseline", "baseline",
                     S.aggregate(base_cases, ratios, within), dev, ratios, k, within, penalty, dist)

    print(json.dumps({"A_market": a["overall"], "B_random": b["overall"],
                      "C_baseline": c["overall"], "penalty": round(penalty, 4),
                      "ratio_count_dist": dist}, ensure_ascii=False, indent=2))
    return a, b, c, penalty, dist, ratios


if __name__ == "__main__":
    main()
