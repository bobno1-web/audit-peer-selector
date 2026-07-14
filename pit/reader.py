"""Point-in-Time 리더 — `as_of(date)` 하나만 공개한다.

원칙(LOOP_0F):
  - C-2: engines 는 이 함수로만 데이터 접근.
  - C-3: 모든 재무는 rcept_dt(제출일) 기준 색인. as_of(T)는 rcept_dt <= T 만 반환.
  - 정보 차단벽(ORACLE): features 에는 채점 계정이 없다. targets 는 채점기 전용.

산출물(scripts/pit_build.py)이 만든 parquet 을 읽을 뿐, 데이터를 만들지 않는다.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
EVAL_YEARS = list(range(2015, 2026))
SNAP_MMDD = "-05-15"                                   # 평가시점(매년 5/15)


class Snapshot:
    """as_of(date) 결과. engines 는 .universe/.features 만, 채점기는 .targets 를 쓴다."""
    def __init__(self, as_of_date, universe, features, targets):
        self.as_of = as_of_date
        self.universe = universe
        self.features = features
        self.targets = targets

    def __repr__(self):
        return (f"Snapshot(as_of={self.as_of}, universe={len(self.universe)}, "
                f"features={len(self.features)}, targets={len(self.targets)})")


def _snapshot_year(date):
    """date('YYYY-MM-DD') 이하의 가장 최근 평가시점 연도. 없으면 None."""
    cand = [y for y in EVAL_YEARS if f"{y}{SNAP_MMDD}" <= date]
    return max(cand) if cand else None


def _read_parquet(path):
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _read_universe(y):
    p = PIT / "universe" / f"universe_{y}.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, dtype=str).fillna("")
    df["rcept_dt"] = df["rcept_dt"].map(_iso)
    return df


def _iso(s):
    s = str(s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s.isdigit() else s


def pit_violations(df, as_of_date):
    """rcept_dt > as_of_date 인 행(=미래 정보 유입). 무결성 테스트가 쓴다."""
    if df is None or len(df) == 0 or "rcept_dt" not in df.columns:
        return df.iloc[0:0] if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return df[df["rcept_dt"].astype(str) > as_of_date]


def as_of(date):
    """date('YYYY-MM-DD') 시점 스냅샷. rcept_dt <= date 인 행만 담긴다(미래 차단)."""
    y = _snapshot_year(date)
    if y is None:
        empty = pd.DataFrame()
        return Snapshot(date, empty, empty, empty)

    universe = _read_universe(y)
    scale = _read_parquet(PIT / "features" / "scale" / f"scale_{y}.parquet")
    industry = _read_parquet(PIT / "features" / "industry" / f"industry_{y}.parquet")
    targets = _read_parquet(PIT / "targets" / "ratios" / f"ratios_{y}.parquet")

    # features = scale + industry (채점 계정 없음 = 정보 차단벽). business 는 있으면 별도 접근.
    if len(scale) and len(industry):
        keep = [c for c in ("corp_code", "induty_code") if c in industry.columns]
        features = scale.merge(industry[keep], on="corp_code", how="left")
    else:
        features = scale if len(scale) else industry

    # ★ point-in-time 보장: 조회일 이후 제출분 제거(스냅샷 자체가 <=T 지만 방어적으로 한 번 더).
    if len(features):
        features = features[features["rcept_dt"].astype(str) <= date].reset_index(drop=True)
    if len(targets):
        targets = targets[targets["rcept_dt"].astype(str) <= date].reset_index(drop=True)

    return Snapshot(f"{y}{SNAP_MMDD}", universe, features, targets)
