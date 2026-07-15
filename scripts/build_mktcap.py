#!/usr/bin/env python3
"""시가총액 피처 빌드 (Loop 3 PART 2). ★ point-in-time — 룩어헤드 0 + 캐시(api-budget).

시총 = as_of 시점 시장가 기준. 데이터: FinanceData/marcap(연도별 전종목 일별 시총, 공개).
  - 평가시점 T = {y}-05-15. **T 이하의 마지막 거래일** 시총만 쓴다(<=T → 미래 주가 사용 0).
  - 상장사만 시총 존재(비상장은 유니버스에 stock_code 없음 → 결측, 임의대체 0).
조인: universe_{y}.csv(corp_code, stock_code) ⋈ marcap.Code(=stock_code) → corp_code 별 시총.
캐시: 연도별 marcap 원본(data/pit/features/mktcap/raw/, 무거워 gitignore) — 재실행 시 다운로드 0.
출력: data/pit/features/mktcap/mktcap_{y}.parquet (as_of_date, corp_code, stock_code, 시가총액).
"""
import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "default.yaml"
MK = ROOT / "data" / "pit" / "features" / "mktcap"
RAW = MK / "raw"
UNIV = ROOT / "data" / "pit" / "universe"
MARCAP_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet"
SNAP_MMDD = "-05-15"
MKTCAP_COL = "시가총액"


def log(m):
    print(m, file=sys.stderr, flush=True)


def fetch_year(y):
    """연도별 marcap 원본(전종목 일별). ★ 캐시: 있으면 다운로드 0."""
    raw_path = RAW / f"marcap-{y}.parquet"
    if raw_path.exists():
        return pd.read_parquet(raw_path), True                    # cache hit
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(MARCAP_URL.format(y=y), headers={"User-Agent": "Mozilla/5.0"})
    b = urllib.request.urlopen(req, timeout=120).read()
    df = pd.read_parquet(io.BytesIO(b))
    raw_path.write_bytes(b)
    return df, False                                              # cache miss (downloaded)


def build_year(y):
    df, hit = fetch_year(y)
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    asof = f"{y}{SNAP_MMDD}"
    le = df[df["Date"] <= asof]                                   # ★ T 이하만 (미래 주가 배제)
    if not len(le):
        return None, hit
    last_trd = le["Date"].max()                                  # T 이하 마지막 거래일
    snap = le[le["Date"] == last_trd][["Code", "Marcap"]].copy()
    snap["stock_code"] = snap["Code"].astype(str).str.zfill(6)
    univ = pd.read_csv(UNIV / f"universe_{y}.csv", dtype=str)
    univ["stock_code"] = univ["stock_code"].astype(str).str.zfill(6)
    out = univ[["corp_code", "stock_code"]].merge(
        snap[["stock_code", "Marcap"]], on="stock_code", how="left")
    out = out.rename(columns={"Marcap": MKTCAP_COL})
    out["as_of_date"] = asof
    out["last_trade_date"] = last_trd
    out = out[["as_of_date", "corp_code", "stock_code", MKTCAP_COL, "last_trade_date"]]
    MK.mkdir(parents=True, exist_ok=True)
    out.to_parquet(MK / f"mktcap_{y}.parquet", index=False)
    cov = out[MKTCAP_COL].notna().mean()
    log(f"  {asof}: last_trade={last_trd} matched={out[MKTCAP_COL].notna().sum()}/{len(out)} "
        f"cov={cov:.3f} {'(cache)' if hit else '(download)'}")
    return out, hit


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    downloads = 0
    for y in dev:
        _, hit = build_year(y)
        downloads += 0 if hit else 1
    log(f"[budget] mktcap years={len(dev)} downloads(cache_miss)={downloads} "
        f"cache_hit={len(dev)-downloads}")


if __name__ == "__main__":
    main()
