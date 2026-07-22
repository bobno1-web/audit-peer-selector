#!/usr/bin/env python3
"""임의 연도 스냅샷 빌드 — 기존 수집 파이프라인을 '연도'만 확장해 재사용(신설 0). WEB-10 ②.

as_of = Y-05-15, fiscal = (Y-1). ★ 룩어헤드 0: universe(list.json)·재무(fnlttSinglAcntAll)·
시총(marcap ≤T)·성장(≤T 매출)·텍스트(rcept_dt ≤T 사업보고서) 전부 rcept_dt/거래일 ≤ Y-05-15.
★ 확정 엔진은 apply 만 — 이 스크립트는 '데이터 소스'만 만든다. 가중치·임계값 재유도 0.

Phase 1 universe_Y   ← spike_survivorship.build_universes (EVAL_YEARS=[Y])
Phase 2 재무 3계층    ← pit_build_full.build_year/finalize_year (rows_Y.jsonl resume; 020 한도 중단·재개)
Phase 3 mktcap_Y     ← build_mktcap.build_year
Phase 4 growth_Y     ← build_growth 로직(외부 API 0; scale_Y·scale_{Y-1})
Phase 5 text_Y(선택) ← Y-05-15 이전 최신 사업보고서 '사업의 내용' → section_vectors_Y.npz(★기존 npz 불변)

resume: 각 phase 산출물이 있으면 skip. 진행상황 runs/pit_full/snapshot_<Y>.json.
게이트: 시작 시 gate.require_pass("survivorship")(PIT 수집 조건). 미통과면 exit 1.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gate                                             # noqa: E402
import audit_parser as ap                               # noqa: E402
import section_parser as sp                             # noqa: E402
import vector_cache as vc                               # noqa: E402

PIT = ROOT / "data" / "pit"
BIZ = PIT / "features" / "business"
WORK = ROOT / "runs" / "pit_full"


def log(m):
    print(m, file=sys.stderr, flush=True)


def _prog_path(y):
    return WORK / f"snapshot_{y}.json"


def load_prog(y):
    p = _prog_path(y)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"year": y, "phases": {}}


def save_prog(y, prog):
    WORK.mkdir(parents=True, exist_ok=True)
    _prog_path(y).write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Phase 1: universe ─────────────────────────────────────────────────────────
def phase_universe(y, force=False):
    out = PIT / "universe" / f"universe_{y}.csv"
    if out.exists() and not force:
        n = sum(1 for _ in out.open(encoding="utf-8-sig")) - 1
        log(f"[P1 universe_{y}] cache hit ({n} corps) — skip")
        return n
    ss = importlib.import_module("spike_survivorship")
    ss.EVAL_YEARS = [y]                                  # ★ 한 연도만(기존 로직 그대로, 범위만 축소)
    log(f"[P1 universe_{y}] list.json A001 크롤 (FY{y-1}, ≤{y}-05-15, 상장사)…")
    univ, all_count = ss.build_universes()
    ss.write_universes(univ)
    n = len(univ.get(y, {}))
    log(f"[P1 universe_{y}] {n} listed corps (A001 filers {all_count.get(y)})")
    return n


# ── Phase 2: 재무(scale/industry/ratios) ──────────────────────────────────────
def phase_financials(y, force=False):
    need = [PIT / "features/scale" / f"scale_{y}.parquet",
            PIT / "features/industry" / f"industry_{y}.parquet",
            PIT / "targets/ratios" / f"ratios_{y}.parquet"]
    if all(p.exists() for p in need) and not force:
        log(f"[P2 financials_{y}] cache hit — skip")
        return "done"
    pf = importlib.import_module("pit_build_full")
    pf.YEARS = [y]                                       # ★ 한 연도만
    log(f"[P2 financials_{y}] fnlttSinglAcntAll(FY{y-1}) + company.json(induty) 수집…")
    result = pf.build_year(y, {})                        # rows_Y.jsonl append; resume 내장
    if result == "limit":
        log("[P2] 020 DART 한도초과 — 진행 저장. 다음 실행 시 rows 이어받기.")
        return "limit"
    pf.finalize_year(y)                                  # rows → 3계층 parquet
    log(f"[P2 financials_{y}] finalize 완료")
    return "done"


# ── Phase 3: mktcap ───────────────────────────────────────────────────────────
def phase_mktcap(y, force=False):
    out = PIT / "features/mktcap" / f"mktcap_{y}.parquet"
    if out.exists() and not force:
        log(f"[P3 mktcap_{y}] cache hit — skip")
        return
    bm = importlib.import_module("build_mktcap")
    log(f"[P3 mktcap_{y}] marcap-{y} (≤{y}-05-15 마지막 거래일)…")
    res, hit = bm.build_year(y)
    if res is None:
        log(f"[P3 mktcap_{y}] ★경고: {y}-05-15 이하 거래일 없음(연초 스냅샷?) — 시총 결측 처리")


# ── Phase 4: growth (외부 API 0) ──────────────────────────────────────────────
def phase_growth(y, force=False):
    out = PIT / "features/growth" / f"growth_{y}.parquet"
    if out.exists() and not force:
        log(f"[P4 growth_{y}] cache hit — skip")
        return
    bg = importlib.import_module("build_growth")
    cur, prev = bg._rev(y), bg._rev(y - 1)
    if cur is None:
        log(f"[P4 growth_{y}] scale_{y} 없음 — skip")
        return
    if prev is None:
        g = cur[["corp_code"]].copy(); g[bg.GROWTH_COL] = pd.NA
    else:
        m = cur.merge(prev, on="corp_code", how="left")
        ok = (m[f"rev_{y}"] > 0) & (m[f"rev_{y-1}"] > 0)
        g = m[["corp_code"]].copy()
        g[bg.GROWTH_COL] = (m[f"rev_{y}"] / m[f"rev_{y-1}"] - 1.0).where(ok)
    g.insert(0, "as_of_date", f"{y}-05-15")
    bg.OUT.mkdir(parents=True, exist_ok=True)
    g.to_parquet(bg.OUT / f"growth_{y}.parquet", index=False)
    log(f"[P4 growth_{y}] n={len(g)} coverage={float(g[bg.GROWTH_COL].notna().mean()):.3f}")


# ── Phase 5: text 최신화 (★ 기존 section_vectors.npz 불변; 연도별 별도 파일) ────
def _fresh_ledger(y):
    """Y-05-15 이전 '최신' FY(Y-1) 사업보고서(A001)의 (rcept_no, rcept_dt). ★ 최신 제출본(정정 후 최종).
    기존 collect_section_text 는 '최이른 dev' 였으나, 스냅샷 Y 의 PIT 텍스트는 ≤T 최신 사업보고서다."""
    led_path = BIZ / f"ledger_{y}.parquet"
    if led_path.exists():
        df = pd.read_parquet(led_path)
        log(f"[P5 ledger_{y}] cache hit ({len(df)} corps)")
        return {r.corp_code: (r.rcept_no, r.rcept_dt) for r in df.itertuples()}
    import re
    PERIOD = re.compile(r"\((\d{4})\.(\d{2})\)")
    fy = y - 1
    best = {}
    for a, b in (("0101", "0315"), ("0316", "0515")):
        page = 1
        while True:
            res = ap.get_json("list.json", {"bgn_de": f"{y}{a}", "end_de": f"{y}{b}",
                                            "pblntf_detail_ty": "A001",
                                            "page_no": str(page), "page_count": "100"})
            if res.get("status") != "000":
                break
            for r in res.get("list", []) or []:
                ms = PERIOD.findall(r.get("report_nm") or "")
                if not ms or int(ms[-1][0]) != fy:       # FY(Y-1) 사업보고서만
                    continue
                cc = (r.get("corp_code") or "").strip()
                dt = (r.get("rcept_dt") or "").strip()
                rn = (r.get("rcept_no") or "").strip()
                if cc and rn and dt <= f"{y}0515" and (cc not in best or dt > best[cc][1]):
                    best[cc] = (rn, dt)                   # ★ 최신(가장 늦은 ≤T) 제출본
            if page >= int(res.get("total_page") or 1):
                break
            page += 1
            time.sleep(0.02)
    pd.DataFrame([{"corp_code": c, "rcept_no": v[0], "rcept_dt": v[1]} for c, v in best.items()]) \
        .to_parquet(led_path, index=False)
    log(f"[P5 ledger_{y}] {len(best)} corps")
    return best


def phase_text(y, force=False):
    import yaml
    cfg = yaml.safe_load((ROOT / "config/default.yaml").read_text(encoding="utf-8"))["similarity"]
    title = cfg["text_section_title"]
    n, vocab = int(cfg["text_ngram"]), int(cfg["text_vocab_size"])
    sectxt_path = BIZ / f"section_text_{y}.parquet"
    outnpz = BIZ / f"section_vectors_{y}.npz"
    if outnpz.exists() and not force:
        log(f"[P5 section_vectors_{y}] cache hit — skip")
        return

    # 유니버스 corp 집합(스냅샷 Y 랭킹 대상)
    uni = pd.read_csv(PIT / "universe" / f"universe_{y}.csv", dtype=str).fillna("")
    corps = set(uni["corp_code"])
    ledger = _fresh_ledger(y)

    have = {}
    if sectxt_path.exists():
        prev = pd.read_parquet(sectxt_path)
        have = {r.corp_code: (r.rcept_dt, r.section_text, r.status) for r in prev.itertuples()}
    rows = [{"corp_code": c, "rcept_dt": have[c][0], "section_text": have[c][1], "status": have[c][2]}
            for c in have]
    todo = [c for c in corps if c in ledger and c not in have]
    log(f"[P5 text_{y}][budget] universe={len(corps)} cache_hit={len(have)} to_fetch={len(todo)}")
    fetched = 0
    for i, cc in enumerate(todo, 1):
        if i % 200 == 1:                                 # 주기적 020 한도 점검
            st = ap.get_json("fnlttSinglAcntAll.json", {"corp_code": cc, "bsns_year": str(y - 1),
                                                        "reprt_code": "11011", "fs_div": "OFS"})
            if st.get("status") == "020":
                log("[P5] 020 한도 — 저장 후 중단(재개 가능).")
                break
        rn, dt = ledger[cc]
        try:
            raw = ap.fetch_doc_text(rn)
            text, status = sp.extract_section(raw, title)
        except Exception as e:                           # noqa: BLE001
            text, status = "", f"error:{type(e).__name__}"
        fetched += 1
        rows.append({"corp_code": cc, "rcept_dt": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
                     "section_text": text, "status": status})
        if i % 200 == 0:
            pd.DataFrame(rows).to_parquet(sectxt_path, index=False)
            log(f"[P5 text_{y}] fetched {i}/{len(todo)}")
        time.sleep(0.03)
    df = pd.DataFrame(rows)
    df.to_parquet(sectxt_path, index=False)
    n_ok = int((df["status"] == "ok").sum())
    log(f"[P5 text_{y}] section_text {len(df)} 저장 new_fetch={fetched} ok={n_ok}")

    # 벡터화 — ★ build_section_vectors 와 동일 벡터라이저(문자 3-gram TF-IDF, L2). 별도 npz.
    bsv = importlib.import_module("build_section_vectors")
    ok = df[(df["status"] == "ok") & (df["section_text"].astype(str).str.len() > 0)].reset_index(drop=True)
    items = list(zip(ok["corp_code"].astype(str), ok["section_text"].astype(str)))
    version = f"{bsv.VERSION}|ngram={n}|vocab={vocab}"
    mat, keys, meta, from_cache = vc.build_or_load(outnpz, items, version, bsv.make_vectorizer(n, vocab))
    log(f"[P5 section_vectors_{y}] {mat.shape} keys={len(keys)} → {outnpz}")


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--year", type=int, required=True)
    ap_.add_argument("--skip-text", action="store_true", help="Phase 5(text 최신화) 생략")
    ap_.add_argument("--only-text", action="store_true", help="Phase 5 만 실행(core 완료 후)")
    ap_.add_argument("--force", action="store_true")
    args = ap_.parse_args()
    y = args.year

    gate.require_pass("survivorship")                    # ★ PIT 수집 조건(gates-are-binding)
    prog = load_prog(y)
    log(f"=== build_snapshot_year Y={y} (as_of {y}-05-15, fiscal {y-1}) ===")

    if not args.only_text:
        prog["phases"]["universe"] = phase_universe(y, args.force)
        save_prog(y, prog)
        st = phase_financials(y, args.force)
        prog["phases"]["financials"] = st
        save_prog(y, prog)
        if st == "limit":
            log("core 미완(한도). 재실행으로 이어받기.")
            return 2
        phase_mktcap(y, args.force)
        prog["phases"]["mktcap"] = "done"
        phase_growth(y, args.force)
        prog["phases"]["growth"] = "done"
        save_prog(y, prog)
        log(f"=== CORE 완료: universe/scale/industry/ratios/mktcap/growth _{y} ===")

    if not args.skip_text:
        phase_text(y, args.force)
        prog["phases"]["text"] = "done"
        save_prog(y, prog)
    log(f"=== build_snapshot_year Y={y} 종료 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
