#!/usr/bin/env python3
"""PART E — PIT 전량 구축 (유니버스 전량 × 2016~2025). 게이트 PASS 후에만 실행된다.

★ 시작 즉시 gate.require_pass("survivorship") 를 호출한다. 게이트가 PASS(사람 승인)가
  아니면 즉시 exit 1. 게이트가 문서가 아니라 실행 조건이다(LOOP_0G B-3).

재개(resume): 진행상황을 runs/pit_full/ 에 기록. 중단·한도초과(020) 시 이어받기.
  - runs/pit_full/rows_<Y>.jsonl : 해당 연도 완료 corp 행(체크포인트, append)
  - runs/pit_full/progress.json  : 완료 연도 + 상태
결측 무대체(임의값 금지). 계정명은 config 에서(pit_build 재사용).
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate                                          # noqa: E402  ★ 게이트
import audit_parser as ap                            # noqa: E402
import pit_build as pb                               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
UNIV = PIT / "universe"
WORK = ROOT / "runs" / "pit_full"
YEARS = list(range(2016, 2026))                      # E-2: FY2014 부재로 2015 제외
GATE_ID = "survivorship"


def log(m):
    print(m, file=sys.stderr, flush=True)


def load_progress():
    p = WORK / "progress.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"done_years": [], "status": "new"}


def save_progress(prog):
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "progress.json").write_text(json.dumps(prog, ensure_ascii=False, indent=2),
                                        encoding="utf-8")


def done_corps(y):
    f = WORK / f"rows_{y}.jsonl"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["corp_code"]] = r
    return out


def append_row(y, row):
    WORK.mkdir(parents=True, exist_ok=True)
    with open(WORK / f"rows_{y}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def fetch_fin_or_limit(cc, fy):
    """단일 경로 재무 수집 + 한도(020) 감지. 중복 호출 없음."""
    for fs in pb.FS_ORDER:
        res = ap.get_json("fnlttSinglAcntAll.json",
                          {"corp_code": cc, "bsns_year": fy,
                           "reprt_code": pb.REPRT_ANNUAL, "fs_div": fs})
        st = res.get("status")
        if st == "020":
            return "LIMIT", None
        if st == "000" and res.get("list"):
            return res["list"], fs
    return None, None


def build_year(y, induty_cache):
    """유니버스 전량 corp 의 재무를 수집. 이미 처리한 corp 는 건너뜀(resume)."""
    fy = str(y - 1)
    asof = f"{y}-05-15"
    with open(UNIV / f"universe_{y}.csv", encoding="utf-8-sig") as f:
        import csv
        universe = list(csv.DictReader(f))
    have = done_corps(y)
    log(f"  year {y}: universe {len(universe)}, already {len(have)}")
    for i, rec in enumerate(universe, 1):
        cc = rec["corp_code"]
        if cc in have:
            continue
        uni_dt = pb.iso(rec["rcept_dt"])
        lst, fs = fetch_fin_or_limit(cc, fy)
        if lst == "LIMIT":
            log("  [LIMIT] status=020 한도초과 — 진행 저장 후 중단(내일 이어받기).")
            return "limit"
        vals = {a: None for a in pb.FETCH}
        rcept_dt = uni_dt
        if lst:
            fin_dt = pb.iso((lst[0].get("rcept_no") or "")[:8])
            if fin_dt and fin_dt <= asof:
                vals = pb.extract(lst)
                rcept_dt = fin_dt
        if cc not in induty_cache:
            comp = ap.get_json("company.json", {"corp_code": cc})
            induty_cache[cc] = (comp.get("induty_code") or "").strip()
            time.sleep(0.02)
        append_row(y, {"as_of_date": asof, "corp_code": cc, "corp_name": rec["corp_name"],
                       "rcept_dt": rcept_dt, "fs_div": fs or "", "induty_code": induty_cache[cc],
                       **{a: vals[a] for a in pb.FETCH}})
        if i % 200 == 0:
            log(f"    {y}: {i}/{len(universe)}")
        time.sleep(0.02)
    return "done"


def finalize_year(y):
    """rows_<Y>.jsonl → data/pit 의 3개 레이어 parquet."""
    rows = list(done_corps(y).values())
    if not rows:
        return
    df = pd.DataFrame(rows)
    scale = df[["as_of_date", "corp_code", "corp_name", "rcept_dt", "fs_div"] + pb.SCALE_ACCOUNTS]
    ind = df[["as_of_date", "corp_code", "corp_name", "rcept_dt", "induty_code"]]
    tgt = df[["as_of_date", "corp_code", "corp_name", "rcept_dt", "fs_div"] + pb.REQUIRED]
    for sub, stem, d, amt in (("features/scale", "scale", scale, pb.SCALE_ACCOUNTS),
                              ("features/industry", "industry", ind, []),
                              ("targets/ratios", "ratios", tgt, pb.REQUIRED)):
        d = d.copy()
        for c in amt:
            d[c] = d[c].astype("Int64")
        (PIT / sub).mkdir(parents=True, exist_ok=True)
        d.to_parquet(PIT / sub / f"{stem}_{y}.parquet", index=False)


def main():
    gate.require_pass(GATE_ID)                        # ★ 게이트: 미통과면 여기서 exit 1
    prog = load_progress()
    prog["status"] = "running"
    save_progress(prog)
    induty_cache = {}
    for y in YEARS:
        if y in prog["done_years"]:
            continue
        result = build_year(y, induty_cache)
        if result == "limit":
            prog["status"] = "limit_hit"
            save_progress(prog)
            log("중단(한도). 다음 실행 시 이어받기.")
            return 2
        finalize_year(y)
        prog["done_years"].append(y)
        save_progress(prog)
        log(f"  year {y} finalize 완료.")
    prog["status"] = "done"
    save_progress(prog)
    log("PIT 전량 구축 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
