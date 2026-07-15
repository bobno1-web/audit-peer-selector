#!/usr/bin/env python3
"""baseline 엔진 — 산업분류 + 규모만 쓰는 기준선 (Loop 1).

각 (타겟 i, 시점 T)에서 as_of(T) 유니버스 전체를 랭킹해 상위 k peer 를 뽑는다.
  랭킹 키 = (산업 tier, 규모 로그거리)   ← 필터가 아니라 스코어링(전 유니버스에 순위).
    - 산업 tier: config prefixes 우선순위(완전일치>2자리>그외). 산업 달라도 배제하지 않는다.
    - 규모 거리: 로그(매출액·총자산) 유클리드. 결측은 거리 최대(뒤로) — 배제/대체 아님.
모든 상수는 config. 종목코드/회사명 리터럴 없음. as_of 로만 접근(룩어헤드 차단).
★ scoring/ 도 targets/ 도 건드리지 않는다(as_of 는 with_targets=False 로 features 만).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pit import as_of                                    # noqa: E402

CONFIG = ROOT / "config" / "default.yaml"


def load_cfg():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _log_pos(series):
    v = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, np.log(v), np.nan)


def rank_peers(feats, cfg):
    """전 유니버스 랭킹 → 각 타겟의 상위 k peer(코드 리스트). (필터 아님.)"""
    k = int(cfg["k"])
    bc = cfg["baseline"]
    prefixes = list(bc["industry_tier_prefixes"])
    codes = feats["corp_code"].to_numpy()
    induty = feats["induty_code"].fillna("").astype(str).to_numpy()
    scale_cols = bc["scale_features"]
    logs = [_log_pos(feats[c]) for c in scale_cols]       # 로그 규모들
    keys = {p: np.array([s[:p] for s in induty]) for p in prefixes}
    n = len(codes)
    out = {}
    for i in range(n):
        # 산업 tier: prefixes 순서대로 일치하면 그 tier. 아무 것도 안 맞으면 최하 tier.
        tier = np.full(n, len(prefixes), dtype=float)
        for ti, p in enumerate(reversed(prefixes)):       # 뒤(넓은)부터 덮어써 앞(좁은)이 우선
            t = len(prefixes) - 1 - ti
            same = (keys[p] == keys[p][i]) & (induty != "")
            tier = np.where(same, t, tier)
        # 규모 로그거리(결측 → inf = 뒤로)
        dist2 = np.zeros(n)
        for lg in logs:
            dist2 = dist2 + (lg - lg[i]) ** 2
        dist = np.sqrt(dist2)
        dist = np.where(np.isnan(dist), np.inf, dist)
        tier[i] = np.inf                                  # 자기 자신 제외(뒤로)
        order = np.lexsort((dist, tier))                  # 1차 tier, 2차 dist
        order = order[order != i][:k]
        out[codes[i]] = [codes[j] for j in order]
    return out


def run(years, run_dir):
    cfg = load_cfg()
    rows = []
    for y in years:
        T = f"{y}-05-15"
        snap = as_of(T)                                   # with_targets=False (엔진)
        feats = snap.features
        if not len(feats):
            continue
        peers = rank_peers(feats, cfg)
        for target, plist in peers.items():
            for rank, p in enumerate(plist, 1):
                rows.append({"corp_code": target, "as_of": T, "rank": rank, "peer_code": p})
        print(f"  {T}: {len(feats)} 타겟 랭킹", file=sys.stderr, flush=True)
    df = pd.DataFrame(rows)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(run_dir / "peers.parquet", index=False)
    return df


def _dev_years_with_data():
    """dev 연도(config) 중 실제 피처 데이터가 있는 연도만. (2015는 FY2014 부재로 자동 제외.)
    ★ 연도 리터럴 하드코딩 대신 데이터 존재로 판정 — holdout 은 포함하지 않는다."""
    cfg = load_cfg()
    dev = cfg["pit_split"]["dev_years"]
    scale_dir = ROOT / "data" / "pit" / "features" / "scale"
    return [y for y in dev if (scale_dir / f"scale_{y}.parquet").exists()]


if __name__ == "__main__":
    out = ROOT / "runs" / "2026-07-15_loop1_baseline"
    run(_dev_years_with_data(), out)                     # dev만. holdout 안 엶.
    print(f"baseline peers → {out}/peers.parquet")
