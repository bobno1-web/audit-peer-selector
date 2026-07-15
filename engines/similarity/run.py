#!/usr/bin/env python3
"""similarity 엔진 — 산업·규모·텍스트 유사도의 '가중 점수' 합산 랭킹 (Loop 2).

baseline(산업 우선 lexicographic)과 달리, 세 피처 유사도를 가중합해 전 유니버스를 랭킹(필터 아님).
  - 산업 유사도: 접두 tier(완전>2자리)에서 유도(1.0/0.5/0).
  - 규모 유사도: 로그(매출액·총자산) 거리 → exp(-dist). 결측 → 0.
  - 텍스트 유사도: 사업내용 TF-IDF 코사인(캐시). 결측 → 0.
가중치는 손으로 안 정한다 — dev 탐색 결과(runs/…similarity/weights.json)를 읽는다(holdout 미사용).
★ scoring/·targets/ 접근 0. as_of(with_targets=False)로 features 만. 매직상수/리터럴 0(config).
★ 데이터층 게이트(data_layer) PASS 후에만 실행(gate.require_pass).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from pit import as_of                                    # noqa: E402
import gate                                              # noqa: E402

CONFIG = ROOT / "config" / "default.yaml"
TXTVEC = ROOT / "data" / "pit" / "features" / "business" / "text_vectors.npz"
RUN = ROOT / "runs" / "2026-07-15_loop2_similarity"


def load_cfg():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def load_text_vectors():
    if not TXTVEC.exists():
        return {}, None
    z = np.load(TXTVEC, allow_pickle=True)
    codes = [str(c) for c in z["corp_codes"]]
    return {c: i for i, c in enumerate(codes)}, z["matrix"].astype(np.float32)


def _log_pos(series):
    v = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, np.log(v), np.nan)


def year_arrays(feats, cfg, txt_idx, txt_mat):
    codes = feats["corp_code"].to_numpy()
    induty = feats["induty_code"].fillna("").astype(str).to_numpy()
    prefixes = list(cfg["similarity"]["industry_prefixes"])
    keys = {p: np.array([s[:p] for s in induty]) for p in prefixes}
    logs = [_log_pos(feats[c]) for c in cfg["similarity"]["scale_features"]]
    # 텍스트 행렬을 올해 코드 순서로 정렬(없으면 0행)
    dim = txt_mat.shape[1] if txt_mat is not None else 0
    tmat = np.zeros((len(codes), dim), dtype=np.float32)
    if txt_mat is not None:
        for r, c in enumerate(codes):
            j = txt_idx.get(str(c))
            if j is not None:
                tmat[r] = txt_mat[j]
    return codes, induty, keys, prefixes, logs, tmat


def rank(feats, cfg, weights, txt_idx, txt_mat, k, target_idx=None):
    codes, induty, keys, prefixes, logs, tmat = year_arrays(feats, cfg, txt_idx, txt_mat)
    n = len(codes)
    w = np.array(weights, dtype=float)
    w = w / w.sum() if w.sum() > 0 else w
    out = {}
    for i in (range(n) if target_idx is None else target_idx):
        tier = np.full(n, len(prefixes), dtype=float)
        for ti, p in reversed(list(enumerate(prefixes))):
            tier = np.where((keys[p] == keys[p][i]) & (induty != ""), ti, tier)
        ind_sim = np.where(tier < len(prefixes), 1.0 - tier / len(prefixes), 0.0)
        d2 = np.zeros(n)
        for lg in logs:
            d2 = d2 + (lg - lg[i]) ** 2
        scale_sim = np.exp(-np.sqrt(d2))
        scale_sim = np.where(np.isnan(scale_sim), 0.0, scale_sim)
        text_sim = tmat @ tmat[i] if tmat.shape[1] else np.zeros(n)
        total = w[0] * ind_sim + w[1] * scale_sim + w[2] * text_sim
        total[i] = -np.inf
        order = np.argsort(total)[::-1][:k]
        out[codes[i]] = [codes[j] for j in order]
    return out


def run(years, weights, run_dir, guard=True):
    if guard:
        gate.require_pass("data_layer")                  # ★ 데이터 게이트 PASS 후에만
    cfg = load_cfg()
    k = int(cfg["k"])
    txt_idx, txt_mat = load_text_vectors()
    rows = []
    for y in years:
        T = f"{y}-05-15"
        feats = as_of(T).features                        # with_targets=False
        if not len(feats):
            continue
        peers = rank(feats, cfg, weights, txt_idx, txt_mat, k)
        for target, plist in peers.items():
            for r, p in enumerate(plist, 1):
                rows.append({"corp_code": target, "as_of": T, "rank": r, "peer_code": p})
        print(f"  {T}: {len(feats)} 타겟 랭킹", file=sys.stderr, flush=True)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(run_dir / "peers.parquet", index=False)
    return pd.DataFrame(rows)


def _dev_years():
    cfg = load_cfg()
    sd = ROOT / "data" / "pit" / "features" / "scale"
    return [y for y in cfg["pit_split"]["dev_years"] if (sd / f"scale_{y}.parquet").exists()]


if __name__ == "__main__":
    wf = RUN / "weights.json"
    weights = json.loads(wf.read_text(encoding="utf-8"))["weights"] if wf.exists() else [1, 1, 1]
    run(_dev_years(), weights, RUN)
    print(f"similarity peers (weights={weights}) → {RUN}/peers.parquet")
