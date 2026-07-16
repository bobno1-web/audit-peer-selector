#!/usr/bin/env python3
"""L6 공식 산출물 — peers.parquet(top-k) + scores.json(canonical) + weights.json. dev 전용.

★ L6 = L4 선정(5축·L4 가중치) + 예측 median@k=10. k=10 은 '엔진이 top-10 peer 를 출력'으로 표현되고,
  **동결 canonical 채점기**(score._cases_from_peers, median)가 그 10개의 중앙값을 자동으로 취한다 →
  scorer 무변경(ORACLE median 동결 준수). k 만 config(prediction.k).
★ 교정 targets(PART0)로 채점. holdout 미개봉. penalty·케이스셋·min_peers 동일.
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
import score as S                                           # noqa: E402
import loop6_predict as LP                                  # noqa: E402
import provenance as PV                                     # noqa: E402

RUN = ROOT / "runs" / "2026-07-16_loop6"
L4 = ROOT / "runs" / "2026-07-15_loop4_similarity"


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    rnames = [r["name"] for r in ratios]
    within = cfg["within"]
    min_peers = int(cfg["min_valid_peers"])
    KL6 = int(cfg["prediction"]["k"])
    ys, Ts = LP.dev_Ts(cfg)
    tables, markets = S.ratio_tables(ys, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios),
                               float(cfg["penalty"]["quantile"]))

    # L6 peers = L4 선정 top-KL6 + 유사도점수
    peers_sim = LP.l4_peers_with_sim(cfg, Ts, KL6)
    rows = []
    for T, pm in peers_sim.items():
        for corp, plist in pm.items():
            for r, (p, s) in enumerate(plist[:KL6], 1):
                rows.append({"corp_code": corp, "as_of": T, "rank": r, "peer_code": p, "sim": s})
    peers = pd.DataFrame(rows)
    RUN.mkdir(parents=True, exist_ok=True)
    peers.to_parquet(RUN / "peers.parquet", index=False)
    # ★ 출처: 라벨 k 가 실제 peer 수와 일치하는지 강제(거짓 라벨 방지, R6/R9)
    k_actual = PV.peers_k(RUN / "peers.parquet")
    assert k_actual == KL6, f"[PROVENANCE] 라벨 k={KL6} ≠ 실제 peer 수 {k_actual}(stale k)"

    # ★ 동결 canonical 채점기(median over top-KL6) — 이것이 곧 median@k10
    cases = S._cases_from_peers(peers, tables, ratios, penalty, min_peers)
    # 자기검증: canonical(top-10) == LP.cases_predict(median, k=10)
    mine = LP.cases_predict(peers_sim, tables, ratios, penalty, min_peers, LP.AGG["median"], KL6)
    eq = abs(float(pd.DataFrame(cases)["ape"].median())
             - float(pd.DataFrame(mine)["ape"].median())) < 1e-9
    agg = S.aggregate(cases, ratios, within)
    dist, _ = S.ratio_count_distribution(tables, ratios)

    # 안정(예측불가 분리) 지표
    flag, tau, _ = LP.separation(Ts, ratios, float(cfg["separation"]["numerator_over_assets_quantile"]))
    sr = LP.split_report(cases, flag)

    obj = {"run_id": RUN.name, "engine": "similarity_l6",
           "as_of": Ts, "k": KL6, "k_actual": k_actual,
           "weights": json.loads((L4 / "weights.json").read_text(encoding="utf-8"))["weights"],
           "components": LP.L4_ORDER, "prediction": {"method": "median", "k": KL6},
           "ratios": rnames, "split": "dev", "targets": "corrected(PART0 receivable fix)",
           "provenance": PV.stamp(ys),                       # ★ 실제 target 데이터 지문(라벨↔실제 결속)
           "n_cases_total": agg["n_cases"], "overall": agg["overall"], "per_ratio": agg["per_ratio"],
           "params": {"penalty_ape": round(penalty, 4)}, "ratio_count_distribution_pct": dist,
           "separation": {"q_sep": float(cfg["separation"]["numerator_over_assets_quantile"]),
                          "excl_rate": sr["excl_rate"],
                          "stable_ape_median": round(sr["stable_median"], 4),
                          "overall_ape_median": round(sr["overall_median"], 4)},
           "canonical_eq_median_k10": bool(eq)}
    (RUN / "scores.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN / "weights.json").write_text(json.dumps(
        {"weights": obj["weights"], "order": LP.L4_ORDER,
         "note": "L6 = L4 선정(5축·L4 가중치) 고정 + 예측 median@k=10(dev 선택, D-028). 새 가중치 학습 없음.",
         "prediction_k": KL6}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": agg["overall"], "canonical_eq": eq,
                      "stable": obj["separation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
