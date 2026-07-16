#!/usr/bin/env python3
"""holdout 개봉 전 dev 설정 동결 (Loop 7 PART 0) — ★ holdout 미접근(dev 전용).

holdout 을 열기 전에 '무엇을 적용할지'를 dev 에서 확정해 파일로 동결한다. 개봉 후 이 값을 바꾸면
부정(freeze 해시로 검증). 여기서 유도하는 모든 상수(penalty·τ_r)는 **dev(교정 targets)에서만** 나온다.

동결 내용:
  - 엔진별 (components, weights, k, text_source): baseline/L2/L3/L4/L6 커밋 산출물에서.
  - penalty_ape: dev 시장중앙값(대조군A) APE 상위꼬리 분위수(q=0.9). ORACLE 상수 규칙.
  - separation τ_r: dev 의 s=|분자|/총자산 하위 q_sep 분위수(D-027). 비율별.
  - dev 교정 targets 지문(d5db24e4…) — 교정본 사용 증거.
출력: config/holdout_freeze.json + 그 SHA-256(콘솔). 개봉 후 해시 불변 검증(holdout_apply).
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
import score as S                                           # noqa: E402
import loop6_predict as LP                                  # noqa: E402
import provenance as PV                                     # noqa: E402

RUNS = ROOT / "runs"
FREEZE = ROOT / "config" / "holdout_freeze.json"
WEIGHTS = {"similarity_L2": "2026-07-15_loop2_similarity",
           "similarity_L3": "2026-07-15_loop3_similarity",
           "similarity_L4": "2026-07-15_loop4_similarity"}


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    q_sep = float(cfg["separation"]["numerator_over_assets_quantile"])
    ys, Ts = LP.dev_Ts(cfg)                                 # dev 연도(교정 targets)
    tables, markets = S.ratio_tables(ys, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios),
                               float(cfg["penalty"]["quantile"]))
    _, tau, _ = LP.separation(Ts, ratios, q_sep)            # dev τ_r

    engines = {
        "baseline": {"type": "baseline", "k": int(cfg["k"]),
                     "params": cfg["baseline"]},
    }
    for name, d in WEIGHTS.items():
        wj = json.loads((RUNS / d / "weights.json").read_text(encoding="utf-8"))
        text_src = "full" if name == "similarity_L2" else "section"
        engines[name] = {"type": "similarity", "components": wj["order"],
                         "weights": wj["weights"], "k": int(cfg["k"]),
                         "text_source": text_src, "prediction": "median"}
    l4 = json.loads((RUNS / WEIGHTS["similarity_L4"] / "weights.json").read_text(encoding="utf-8"))
    engines["similarity_L6"] = {"type": "similarity", "components": l4["order"],
                                "weights": l4["weights"], "k": int(cfg["prediction"]["k"]),
                                "text_source": "section", "prediction": "median",
                                "note": "L4 선정축 + median@k=10 + 예측불가분리(τ_r)"}

    freeze = {
        "created": "Loop 7 PART 0 — holdout 개봉 전 dev 동결(holdout 미접근)",
        "dev_years": ys,
        "ratios": [{"name": r["name"], "numerator": r["numerator"],
                    "denominator": r["denominator"]} for r in ratios],
        "min_valid_peers": int(cfg["min_valid_peers"]),
        "penalty_ape": round(penalty, 6),
        "separation": {"q_sep": q_sep, "tau_by_ratio": {k: round(v, 8) for k, v in tau.items()}},
        "dev_corrected_targets_digest": PV.combined_targets_digest(ys),
        "engines": engines,
        "policy": "holdout 에는 이 값들을 그대로 적용만 한다. 재학습·재유도·k변경 금지. "
                  "penalty·τ_r 은 dev 유도(holdout 시장·분포 참조 금지).",
    }
    body = json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True)
    FREEZE.write_text(body, encoding="utf-8")
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    print(f"freeze written: {FREEZE}")
    print(f"penalty_ape={freeze['penalty_ape']}  tau={freeze['separation']['tau_by_ratio']}")
    print(f"dev_digest={freeze['dev_corrected_targets_digest'][:16]}…")
    print(f"FREEZE_SHA256={h}")
    (ROOT / "config" / "holdout_freeze.sha256").write_text(h, encoding="utf-8")


if __name__ == "__main__":
    main()
