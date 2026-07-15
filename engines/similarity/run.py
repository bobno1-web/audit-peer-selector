#!/usr/bin/env python3
"""similarity 엔진 — 다축 유사도의 '가중 점수' 합산 랭킹.

Loop 2: 3축(산업·규모·텍스트[전문]).  ★ Loop 3: 4축(산업·규모·**시총**·텍스트[**섹션**]).
구성 요소는 config(similarity.components)에서 온다 — 개수/순서가 곧 가중치 순서.
  - industry: 접두 tier(완전>2자리)에서 유도한 유사도(1.0/0.5/0).
  - scale   : 로그(매출액·총자산) 유클리드 거리 → exp(-d). 결측 → 0.
  - mktcap  : 로그(시가총액) 거리 → exp(-|d|). 결측 → 0. (as_of 시점 시총, 룩어헤드 0)
  - text    : '사업의 내용' 섹션 TF-IDF 코사인(캐시). 결측 → 0.
가중치는 손으로 안 정한다 — dev 탐색 결과(runs/…/weights.json)를 읽는다(holdout 미사용).
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
TXTVEC = ROOT / "data" / "pit" / "features" / "business" / "section_vectors.npz"
RUN = ROOT / "runs" / "2026-07-15_loop3_similarity"


def load_cfg():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def load_text_vectors():
    """섹션 벡터 캐시(Loop 3). 없으면 빈 결과 → 텍스트 유사도 0."""
    if not TXTVEC.exists():
        return {}, None
    z = np.load(TXTVEC, allow_pickle=True)
    key = "keys" if "keys" in z else "corp_codes"
    codes = [str(c) for c in z[key]]
    return {c: i for i, c in enumerate(codes)}, z["matrix"].astype(np.float32)


def _log_pos(series):
    v = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, np.log(v), np.nan)


def year_arrays(feats, cfg, txt_idx, txt_mat):
    """연도 스냅샷의 성분별 기저 배열을 미리 계산(성분 유사도 정의는 sim_* 참조)."""
    scfg = cfg["similarity"]
    codes = feats["corp_code"].to_numpy()
    induty = feats["induty_code"].fillna("").astype(str).to_numpy()
    prefixes = list(scfg["industry_prefixes"])
    keys = {p: np.array([s[:p] for s in induty]) for p in prefixes}
    logs = [_log_pos(feats[c]) for c in scfg["scale_features"]]
    mkcol = scfg["mktcap_feature"]
    mklog = _log_pos(feats[mkcol]) if mkcol in feats.columns else np.full(len(codes), np.nan)
    dim = txt_mat.shape[1] if txt_mat is not None else 0
    tmat = np.zeros((len(codes), dim), dtype=np.float32)
    if txt_mat is not None:
        for r, c in enumerate(codes):
            j = txt_idx.get(str(c))
            if j is not None:
                tmat[r] = txt_mat[j]
    return {"codes": codes, "induty": induty, "keys": keys, "prefixes": prefixes,
            "logs": logs, "mklog": mklog, "tmat": tmat}


def sim_industry(A, i):
    keys, prefixes, induty = A["keys"], A["prefixes"], A["induty"]
    n = len(A["codes"])
    tier = np.full(n, len(prefixes), dtype=float)
    for ti, p in reversed(list(enumerate(prefixes))):
        tier = np.where((keys[p] == keys[p][i]) & (induty != ""), ti, tier)
    return np.where(tier < len(prefixes), 1.0 - tier / len(prefixes), 0.0)


def sim_scale(A, i):
    d2 = np.zeros(len(A["codes"]))
    for lg in A["logs"]:
        d2 = d2 + (lg - lg[i]) ** 2
    s = np.exp(-np.sqrt(d2))
    return np.where(np.isnan(s), 0.0, s)


def sim_mktcap(A, i):
    mk = A["mklog"]
    s = np.exp(-np.abs(mk - mk[i]))
    return np.where(np.isnan(s), 0.0, s)


def sim_text(A, i):
    tmat = A["tmat"]
    return tmat @ tmat[i] if tmat.shape[1] else np.zeros(len(A["codes"]))


SIMS = {"industry": sim_industry, "scale": sim_scale, "mktcap": sim_mktcap, "text": sim_text}


def rank(feats, cfg, weights, txt_idx, txt_mat, k, target_idx=None):
    comps = list(cfg["similarity"]["components"])
    A = year_arrays(feats, cfg, txt_idx, txt_mat)
    codes = A["codes"]
    n = len(codes)
    w = np.array(weights, dtype=float)
    w = w / w.sum() if w.sum() > 0 else w
    out = {}
    for i in (range(n) if target_idx is None else target_idx):
        total = np.zeros(n)
        for c, comp in enumerate(comps):
            total = total + w[c] * SIMS[comp](A, i)
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
    n_comp = len(load_cfg()["similarity"]["components"])
    weights = json.loads(wf.read_text(encoding="utf-8"))["weights"] if wf.exists() else [1] * n_comp
    run(_dev_years(), weights, RUN)
    print(f"similarity peers (weights={weights}) → {RUN}/peers.parquet")
