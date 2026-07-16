#!/usr/bin/env python3
"""Loop 6 PART 3 — 신경망 임베딩 무료 정찰 (유료 지출 전 최종 판단).

무료 소형 정적 임베딩(model2vec, 다국어 128M, 로컬·pip 설치·torch 불요)으로 '사업의 내용' 섹션을
벡터화하고, **같은 텍스트·같은 격자·같은 SEED/SUB** 로 5축(L4) 그리드를 돌려 TF-IDF 와 비교한다.
유일한 변수 = 텍스트 벡터라이저(문자 3-gram TF-IDF vs 신경망 의미 임베딩).

판정: 신경망 텍스트 축이 (a) 더 큰 학습 가중치를 받나, (b) dev 표본 APE 를 낮추나.
  둘 다 아니면 → 유료 최신 임베딩도 가망 낮음(LOW). 나면 → 유료 고려 가치.
★ 캐싱(api-budget): 신경망 벡터는 (콘텐츠·모델) 메타로 npz 캐시 → 재실행 재계산 0.
★ dev 전용. holdout 미사용. 임베딩은 로컬(유료 API 0).
"""
import hashlib
import json
import random
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
from pit import as_of                                       # noqa: E402
import score as S                                           # noqa: E402
import run as SIM                                           # noqa: E402
import loop4_search as L4S                                  # noqa: E402

B = ROOT / "data" / "pit" / "features" / "business"
SECTXT = B / "section_text.parquet"
NEURAL_NPZ = B / "neural_section_vectors.npz"
MODEL_DIR = ROOT / "data" / "pit" / "cache" / "m2v_multilingual"
MODEL_NAME = "minishlab/potion-multilingual-128M"
RUN = ROOT / "runs" / "2026-07-16_loop6"
SEED = 20260715
SUB = 250
L4_ORDER = ["industry", "scale", "mktcap", "text", "growth"]


def build_or_load_neural():
    """섹션 텍스트 → 신경망 임베딩(L2정규화) npz 캐시. 반환 (idx{corp:row}, matrix)."""
    df = pd.read_parquet(SECTXT)
    df = df[(df["status"] == "ok") & (df["section_text"].astype(str).str.len() > 0)].reset_index(drop=True)
    texts = df["section_text"].astype(str).tolist()
    keys = df["corp_code"].astype(str).tolist()
    meta = hashlib.sha256((MODEL_NAME + "|" + str(len(texts)) + "|"
                           + hashlib.sha256("".join(texts).encode("utf-8")).hexdigest()
                           ).encode()).hexdigest()
    if NEURAL_NPZ.exists():
        z = np.load(NEURAL_NPZ, allow_pickle=True)
        if str(z.get("meta_hash")) == meta:
            print("[cache] neural vectors HIT (재계산 0)", file=sys.stderr)
            return {str(c): i for i, c in enumerate(z["keys"])}, z["matrix"].astype(np.float32)
    from model2vec import StaticModel
    model = StaticModel.from_pretrained(str(MODEL_DIR) if MODEL_DIR.exists() else MODEL_NAME)
    emb = np.asarray(model.encode(texts), dtype=np.float32)
    norm = np.linalg.norm(emb, axis=1, keepdims=True)
    emb = np.divide(emb, norm, out=np.zeros_like(emb), where=norm > 0)
    np.savez(NEURAL_NPZ, matrix=emb, keys=np.array(keys), meta_hash=meta)
    print(f"[cache] neural vectors MISS → 계산·저장 {emb.shape}", file=sys.stderr)
    return {c: i for i, c in enumerate(keys)}, emb


def grid_search(cfg, dev, tables, txt_idx, txt_mat, penalty, min_peers, k):
    """L4 5축 그리드(같은 SEED/SUB) — 주어진 텍스트 벡터로. 반환 (best_weights, best_ape)."""
    comps = L4_ORDER
    cfg = deepcopy(cfg)
    cfg["similarity"]["components"] = comps
    rnames = [r["name"] for r in cfg["ratios"]]
    data, rnd = {}, random.Random(SEED)
    for y in dev:
        T = f"{y}-05-15"
        feats = as_of(T).features
        sub = sorted(rnd.sample(range(len(feats)), min(SUB, len(feats))))
        data[T] = L4S.component_vectors(feats, cfg, txt_idx, txt_mat, sub)
    SA = L4S.build_score_arrays(data, tables, rnames, comps, k)
    import itertools
    grid = cfg["similarity"]["weight_grid"]
    combos = sorted({tuple(np.round(np.array(w) / sum(w), 4))
                     for w in itertools.product(grid, repeat=len(comps)) if sum(w) > 0})
    best, best_ape = None, 1e9
    for w in combos:
        ape = float(np.median(L4S.fast_ape(SA, w, k, penalty, min_peers)))
        if ape < best_ape:
            best, best_ape = list(w), ape
    return dict(zip(comps, best)), round(best_ape, 4), len(combos)


def main():
    cfg = S.load_cfg()
    ratios, k = cfg["ratios"], int(cfg["k"])
    min_peers = int(cfg["min_valid_peers"])
    q = float(cfg["penalty"]["quantile"])
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    tables, markets = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios), q)

    tfidf_idx, tfidf_mat = SIM.load_text_vectors()
    neural_idx, neural_mat = build_or_load_neural()

    tf_w, tf_ape, ncombo = grid_search(cfg, dev, tables, tfidf_idx, tfidf_mat,
                                       penalty, min_peers, k)
    ne_w, ne_ape, _ = grid_search(cfg, dev, tables, neural_idx, neural_mat,
                                  penalty, min_peers, k)

    verdict = ("LOW" if (ne_w["text"] <= tf_w["text"] + 1e-9 and ne_ape >= tf_ape - 1e-9)
               else ("MEDIUM" if ne_ape < tf_ape else "MIXED"))
    out = {"model": MODEL_NAME, "embedding_dim": int(neural_mat.shape[1]),
           "n_texts": int(neural_mat.shape[0]), "grid_combos": ncombo,
           "SEED": SEED, "SUB": SUB, "penalty": round(penalty, 4),
           "tfidf": {"weights": {k2: round(v, 4) for k2, v in tf_w.items()},
                     "text_weight": round(tf_w["text"], 4), "subsample_ape": tf_ape},
           "neural": {"weights": {k2: round(v, 4) for k2, v in ne_w.items()},
                      "text_weight": round(ne_w["text"], 4), "subsample_ape": ne_ape},
           "text_weight_rose": bool(ne_w["text"] > tf_w["text"] + 1e-9),
           "ape_improved": bool(ne_ape < tf_ape - 1e-9),
           "paid_embedding_value": verdict}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "embedding_scout2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
