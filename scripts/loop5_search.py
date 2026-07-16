#!/usr/bin/env python3
"""Loop 5 가중치 탐색 + similarity(6축) 최종 채점.

★ Loop 2/3/4 와 **완전히 동일한 학습 절차·격자·SEED·표본수(SUB)·채점 정의**(P16). 유일한 차이는
  활성 성분 수(config.components = 산업·규모·시총·텍스트·성장·**부문**; 부문 데이터 확보로 활성화).
★ 성능: 격자가 5^6 으로 커져 per-combo 채점을 **벡터화**(loop4 와 동일 코드). 벡터화==canonical 을
  탐색 전 표본 조합에서 검증(max|Δ|<1e-9)하고, **보고 점수는 canonical 경로**(SIM.run+score)로 산출.
best 가중치 → weights.json → SIM.run + canonical 채점 → scores.json.
"""
import itertools
import json
import random
import sys
import warnings
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

SEED = 20260715                                          # ★ Loop 2/3/4 와 동일(유리하게 변경 0)
SUB = 250                                                # ★ Loop 2/3/4 와 동일
RUN = ROOT / "runs" / "2026-07-16_loop5_similarity"


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
    w = np.array(w, float); w = w / w.sum()
    rows = []
    for T, (codes, C, subidx) in data.items():
        total = sum(w[c] * C[comp] for c, comp in enumerate(comps))
        for r, i in enumerate(subidx):
            total[r, i] = -np.inf
            order = np.argsort(total[r])[::-1][:k]
            for rank_, j in enumerate(order, 1):
                rows.append({"corp_code": codes[i], "as_of": T, "rank": rank_, "peer_code": codes[j]})
    return pd.DataFrame(rows)


def build_score_arrays(data, tables, rnames, comps, k):
    SA = {}
    for T, (codes, C, sub) in data.items():
        rt = tables.get(T)
        R = rt.reindex(codes)[rnames].to_numpy(dtype=float) if rt is not None \
            else np.full((len(codes), len(rnames)), np.nan)
        sub = np.asarray(sub)
        A = R[sub]
        Cs = np.stack([C[comp] for comp in comps])
        SA[T] = (R, A, sub, Cs)
    return SA


def fast_ape(SA, w, k, penalty, min_peers):
    w = np.array(w, float); w = w / w.sum()
    out = []
    for T, (R, A, sub, Cs) in SA.items():
        total = np.einsum("c,cij->ij", w, Cs)
        total[np.arange(len(sub)), sub] = -np.inf
        order = np.argpartition(total, -k, axis=1)[:, -k:]
        PR = R[order]
        cnt = (~np.isnan(PR)).sum(axis=1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            pred = np.nanmedian(PR, axis=1)
        defined = (~np.isnan(A)) & (A != 0)
        fail = cnt < min_peers
        with np.errstate(divide="ignore", invalid="ignore"):
            ape = np.where(fail, penalty, np.abs(pred - A) / np.abs(A))
        out.append(ape[defined])
    return np.concatenate(out)


def verify_equivalence(data, SA, comps, tables, ratios, penalty, min_peers, k):
    rnd = random.Random(SEED + 1)
    grid = [0.0, 0.25, 0.5, 0.75, 1.0]
    samples = [tuple(1 if i == j else 0 for i in range(len(comps))) for j in range(len(comps))]
    samples += [tuple(rnd.choice(grid) for _ in comps) for _ in range(6)]
    maxd = 0.0
    for w in samples:
        if sum(w) == 0:
            continue
        fast = float(np.median(fast_ape(SA, w, k, penalty, min_peers)))
        pdf = peers_from_combo(data, comps, w, k)
        canon = float(pd.DataFrame(S._cases_from_peers(pdf, tables, ratios, penalty, min_peers))["ape"].median())
        maxd = max(maxd, abs(fast - canon))
        if abs(fast - canon) > 1e-9:
            raise SystemExit(f"[VERIFY FAIL] w={w} fast={fast} canonical={canon} — 벡터화 불일치, 중단.")
    print(f"[verify] {len(samples)} 표본 조합 벡터화==canonical (max|Δ|={maxd:.2e}<1e-9) ✓", file=sys.stderr)


def main():
    cfg = S.load_cfg()
    ratios, k = cfg["ratios"], int(cfg["k"])
    within, min_peers = cfg["within"], int(cfg["min_valid_peers"])
    q = float(cfg["penalty"]["quantile"])
    comps = list(cfg["similarity"]["components"])
    rnames = [r["name"] for r in ratios]
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    tables, markets = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios), q)
    print(f"penalty={penalty:.4f} (baseline·L2·L3·L4 와 동일 자); components={comps}", file=sys.stderr)

    txt_idx, txt_mat = SIM.load_text_vectors()
    print(f"section text vectors: {'없음' if txt_mat is None else txt_mat.shape}", file=sys.stderr)

    data, rnd = {}, random.Random(SEED)
    for y in dev:
        T = f"{y}-05-15"
        feats = as_of(T).features
        sub = sorted(rnd.sample(range(len(feats)), min(SUB, len(feats))))
        data[T] = component_vectors(feats, cfg, txt_idx, txt_mat, sub)

    SA = build_score_arrays(data, tables, rnames, comps, k)
    verify_equivalence(data, SA, comps, tables, ratios, penalty, min_peers, k)

    grid = cfg["similarity"]["weight_grid"]
    combos = sorted({tuple(np.round(np.array(w) / sum(w), 4))
                     for w in itertools.product(grid, repeat=len(comps)) if sum(w) > 0})
    print(f"grid combos={len(combos)} ({len(comps)}축) — 탐색 시작", file=sys.stderr)
    best, best_ape = None, 1e9
    for n, w in enumerate(combos, 1):
        ape = float(np.median(fast_ape(SA, w, k, penalty, min_peers)))
        if ape < best_ape:
            best, best_ape = list(w), ape
        if n % 1000 == 0:
            print(f"  {n}/{len(combos)} 탐색 (best APE={best_ape:.4f})", file=sys.stderr)
    print(f"best weights {comps}={best}  dev표본 APE중앙값={best_ape:.4f} (combos={len(combos)})",
          file=sys.stderr)

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "weights.json").write_text(json.dumps(
        {"weights": best, "order": comps, "search": "dev grid(벡터화; canonical 검증), holdout 미사용",
         "subsample_APE_median": round(best_ape, 4), "grid": grid, "n_combos": len(combos),
         "seed": SEED, "sub": SUB}, ensure_ascii=False, indent=2), encoding="utf-8")

    full = SIM.run(dev, best, RUN, guard=True)                 # ★ 최종 점수는 canonical 경로
    cases = S._cases_from_peers(full, tables, ratios, penalty, min_peers)
    agg = S.aggregate(cases, ratios, within)
    dist, _ = S.ratio_count_distribution(tables, ratios)
    obj = {"run_id": RUN.name, "engine": "similarity_l5",
           "as_of": [f"{y}-05-15" for y in dev], "k": k, "weights": best, "components": comps,
           "ratios": rnames, "split": "dev",
           "n_cases_total": agg["n_cases"], "overall": agg["overall"], "per_ratio": agg["per_ratio"],
           "params": {"penalty_ape": round(penalty, 4)}, "ratio_count_distribution_pct": dist}
    (RUN / "scores.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"weights": best, "components": comps, "overall": agg["overall"],
                      "per_ratio": {r: agg["per_ratio"][r]["ape_median"] for r in rnames}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
