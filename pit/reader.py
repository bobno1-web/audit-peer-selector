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
def _discover_eval_years():
    """평가시점 연도 = 유니버스 원장이 있는 연도(디스크 발견). ★ 하드코딩 상한 없음 —
    새 스냅샷(예: 2026)을 원장이 생기면 자동 인식. 없으면 기존 범위(2015~2025) 폴백."""
    uni = PIT / "universe"
    ys = set()
    if uni.exists():
        for p in uni.glob("universe_*.csv"):
            s = p.stem.split("_")[-1]
            if len(s) == 4 and s.isdigit():
                ys.add(int(s))
    return sorted(ys) if ys else list(range(2015, 2026))


EVAL_YEARS = _discover_eval_years()
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


def as_of(date, with_targets=False):
    """date('YYYY-MM-DD') 시점 스냅샷. rcept_dt <= date 인 행만 담긴다(미래 차단).

    ★ 정보 차단벽(fail-closed): **기본은 targets 를 로드하지 않는다.** 엔진은 as_of(T) 로 features·
      universe 만 받는다(snap.targets 는 빈 DataFrame). 채점기만 as_of(T, with_targets=True) 로
      targets 를 받는다. 엔진이 실수로 snap.targets 를 봐도 비어 있어 물리적으로 차단된다."""
    y = _snapshot_year(date)
    if y is None:
        empty = pd.DataFrame()
        return Snapshot(date, empty, empty, empty)

    universe = _read_universe(y)
    scale = _read_parquet(PIT / "features" / "scale" / f"scale_{y}.parquet")
    industry = _read_parquet(PIT / "features" / "industry" / f"industry_{y}.parquet")
    mktcap = _read_parquet(PIT / "features" / "mktcap" / f"mktcap_{y}.parquet")
    growth = _read_parquet(PIT / "features" / "growth" / f"growth_{y}.parquet")
    segment = _read_parquet(PIT / "features" / "segment" / f"segment_{y}.parquet")

    # features = scale + industry (+ 시총) (채점 계정 없음 = 정보 차단벽).
    if len(scale) and len(industry):
        keep = [c for c in ("corp_code", "induty_code") if c in industry.columns]
        features = scale.merge(industry[keep], on="corp_code", how="left")
    else:
        features = scale if len(scale) else industry

    # 시가총액(as_of 시점 <=T 시장가로 빌드; 룩어헤드 0). 결측은 결측(임의대체 0).
    if len(features) and len(mktcap) and "시가총액" in mktcap.columns:
        features = features.merge(mktcap[["corp_code", "시가총액"]], on="corp_code", how="left")

    # 매출성장률(T 이전 2개 연차 매출로 계산; 룩어헤드 0). 결측은 결측(Loop 4).
    if len(features) and len(growth) and "매출성장률" in growth.columns:
        features = features.merge(growth[["corp_code", "매출성장률"]], on="corp_code", how="left")

    # 부문 집중도 프로필(사업보고서 부문별 매출 → HHI·최대비중·부문수; 룩어헤드 0). 결측은 결측(Loop 4).
    if len(features) and len(segment):
        segcols = [c for c in ("seg_hhi", "seg_top_share", "seg_n") if c in segment.columns]
        if segcols:
            features = features.merge(segment[["corp_code"] + segcols], on="corp_code", how="left")

    # ★ point-in-time 보장: 조회일 이후 제출분 제거(스냅샷 자체가 <=T 지만 방어적으로 한 번 더).
    if len(features):
        features = features[features["rcept_dt"].astype(str) <= date].reset_index(drop=True)

    targets = pd.DataFrame()
    if with_targets:                                     # ★ 채점기만
        targets = _read_parquet(PIT / "targets" / "ratios" / f"ratios_{y}.parquet")
        if len(targets):
            targets = targets[targets["rcept_dt"].astype(str) <= date].reset_index(drop=True)

    return Snapshot(f"{y}{SNAP_MMDD}", universe, features, targets)
