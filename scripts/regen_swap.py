#!/usr/bin/env python3
"""교정 targets/scale 스왑 (Loop 6 PART 0-3) — 원본 백업 후 dev 년도만 교체.

regen_targets.py 가 만든 staged/ 를 라이브(data/pit)로 스왑한다. dev(2016~2022)만.
★ holdout(2023~2025) 파일은 건드리지 않는다(미개봉; 개봉 시 함께 재생성).
★ 원본을 runs/2026-07-16_regen_targets/original/ 에 백업(되돌리기 가능).
사용: python scripts/regen_swap.py           # 스왑 실행
      python scripts/regen_swap.py --restore # 백업에서 복원
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
RUN = ROOT / "runs" / "2026-07-16_regen_targets"
STAGED = RUN / "staged"
ORIG = RUN / "original"
DEV_YEARS = range(2016, 2023)
LIVE = {"ratios": PIT / "targets" / "ratios", "scale": PIT / "features" / "scale"}


def swap():
    ORIG.mkdir(parents=True, exist_ok=True)
    changed = {"ratios": 0, "scale": 0}
    for kind, live in LIVE.items():
        for y in DEV_YEARS:
            st = STAGED / f"{kind}_{y}.parquet"
            lv = live / f"{kind}_{y}.parquet"
            if not st.exists():
                print(f"  [skip] staged 없음: {st.name}")
                continue
            shutil.copy2(lv, ORIG / f"{kind}_{y}.parquet")     # 백업
            a = pd.read_parquet(lv)
            b = pd.read_parquet(st)
            assert len(a) == len(b), f"row 수 불일치 {kind}_{y}: {len(a)} vs {len(b)}"
            shutil.copy2(st, lv)                                # 스왑
            changed[kind] += 1
    print(f"스왑 완료(dev만): {changed}. 백업 → {ORIG}")


def restore():
    for kind, live in LIVE.items():
        for y in DEV_YEARS:
            bk = ORIG / f"{kind}_{y}.parquet"
            if bk.exists():
                shutil.copy2(bk, live / f"{kind}_{y}.parquet")
    print(f"복원 완료(원본 → 라이브).")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        restore()
    else:
        swap()
