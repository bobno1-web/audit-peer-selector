#!/usr/bin/env python3
"""매출 성장률 축 (Loop 4 PART 2) — ★ 캐시된 scale 파케이만. 외부 API 0. 룩어헤드 0.

성장률(as_of T=y-05-15) = 매출액(scale_y) / 매출액(scale_{y-1}) − 1.
  - scale_y   = T 이전 최신 연차(=FY y−1) 매출액 (rcept_dt ≤ y-05-15).
  - scale_{y-1} = (y−1)-05-15 이전 최신 연차(=FY y−2) 매출액.
  → 두 값 모두 T 이전 제출분 → **미래 매출 미사용(룩어헤드 0)**.
결측(직전연 부재·매출≤0·기업 신규)은 **결측**(임의대체 0). 최이른 연도는 직전 연도 파일이 없어 결측.
출력: data/pit/features/growth/growth_{y}.parquet (as_of_date, corp_code, 매출성장률).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCALE = ROOT / "data" / "pit" / "features" / "scale"
OUT = ROOT / "data" / "pit" / "features" / "growth"
GROWTH_COL = "매출성장률"
REV = "매출액"


def _rev(y):
    p = SCALE / f"scale_{y}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df[REV] = pd.to_numeric(df[REV], errors="coerce")
    return df[["corp_code", REV]].rename(columns={REV: f"rev_{y}"})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    years = sorted(int(p.stem.split("_")[1]) for p in SCALE.glob("scale_*.parquet"))
    total_cov = []
    for y in years:
        cur, prev = _rev(y), _rev(y - 1)
        if cur is None:
            continue
        if prev is None:                                   # 직전 연도 파일 없음 → 전량 결측
            g = cur[["corp_code"]].copy()
            g[GROWTH_COL] = pd.NA
        else:
            m = cur.merge(prev, on="corp_code", how="left")
            ok = (m[f"rev_{y}"] > 0) & (m[f"rev_{y-1}"] > 0)
            g = m[["corp_code"]].copy()
            g[GROWTH_COL] = (m[f"rev_{y}"] / m[f"rev_{y-1}"] - 1.0).where(ok)
        g.insert(0, "as_of_date", f"{y}-05-15")
        g.to_parquet(OUT / f"growth_{y}.parquet", index=False)
        cov = float(g[GROWTH_COL].notna().mean())
        total_cov.append((y, len(g), cov))
        print(f"  growth_{y}: n={len(g)} coverage={cov:.3f}", file=sys.stderr)
    mean_cov = sum(c for _, _, c in total_cov) / max(len(total_cov), 1)
    print(f"[done] growth built for {len(total_cov)} years; mean coverage={mean_cov:.3f}")


if __name__ == "__main__":
    main()
