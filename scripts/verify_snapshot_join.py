#!/usr/bin/env python3
"""스냅샷 합류 검증 (WEB-10 H-2/H-3) — 새 스냅샷(예: 2026)에 ①태그하한이 타당한지 + 오판정 재현.

H-2: 하한(0.52)이 그 연도의 텍스트 벡터에서도 널(다른 KSIC2) p99 근처인지 재확인(재유도 아님, 검증).
H-3: CJ제일제당/오뚜기의 오판정(전선·철강·전자)이 하한으로 사라지고 식품 peer 는 유지되는지 before/after.

★ 순위·유사도·엔진 가중치 불변(apply-only). 표시 라벨(top_axes)만 하한 적용.
사용: python scripts/verify_snapshot_join.py --year 2026
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
import web_engine as W                                   # noqa: E402
import run as SIM                                        # noqa: E402
OUT = ROOT / "runs" / "web10_tag_floor"


def floor_validity_on_year(year, floor):
    """그 연도 서빙에 쓰는 텍스트 벡터로 널(다른 KSIC2) p99 재집계 — 하한 타당성(H-2)."""
    from pit import as_of
    txt_idx, txt_mat = W._load_text_vectors_for(year)
    if txt_mat is None:
        return {"year": year, "error": "no text vectors"}
    feats = as_of(f"{year}-05-15").features
    codes = feats["corp_code"].astype(str).to_numpy()
    induty = feats["induty_code"].fillna("").astype(str).to_numpy()
    rows, ind2 = [], []
    for c, ind in zip(codes, induty):
        j = txt_idx.get(str(c))
        if j is not None and len(ind[:2]) == 2 and ind[:2].strip():
            rows.append(txt_mat[j]); ind2.append(ind[:2])
    M = np.asarray(rows, dtype=np.float32); ind2 = np.asarray(ind2)
    C = M @ M.T
    iu = np.triu_indices(len(M), k=1)
    cos = C[iu]; same = ind2[iu[0]] == ind2[iu[1]]
    cross = cos[~same]
    return {"year": year, "n_firms": int(len(M)),
            "null_p50": round(float(np.quantile(cross, .50)), 4),
            "null_p99": round(float(np.quantile(cross, .99)), 4),
            "floor": floor,
            "floor_vs_null_p99": "close (valid)" if abs(float(np.quantile(cross, .99)) - floor) < 0.03
                                  else "recheck"}


def cj_before_after(year, floor):
    """CJ/오뚜기 peer 의 원 텍스트 코사인 + 하한 전/후 '사업내용' 라벨(H-3)."""
    ctx = W._ctx(year)
    uni = pd.read_csv(ROOT / "data/pit/universe" / f"universe_{year}.csv", dtype=str).fillna("")

    def code_of(name):
        h = uni[uni["corp_name"].str.replace(" ", "") == name.replace(" ", "")]
        return h["corp_code"].iloc[0] if len(h) else None

    txt_label = W.AXIS_LABELS["text"]
    results = []
    for tgt_name in ["CJ제일제당", "오뚜기"]:
        r = W.query(tgt_name, year=year)
        if not r.get("ok"):
            results.append({"target": tgt_name, "ok": False, "reason": r.get("reason")}); continue
        i = ctx["idx"][r["target"]["corp_code"]]
        raw_text = SIM.SIMS["text"](ctx["A"], i)
        peers = []
        for p in r["peers"]:
            j = ctx["idx"].get(p["peer_code"])
            cos = float(raw_text[j]) if j is not None else None
            # before = 하한 미적용 top-2(양수); after = p["top_axes"](하한 적용됨)
            top = sorted(p["rationale"].items(), key=lambda kv: kv[1], reverse=True)
            before = [W.AXIS_LABELS.get(k, k) for k, v in top[:2] if v > 0]
            peers.append({"rank": p["rank"], "peer": p["peer_name"],
                          "raw_text_cos": None if cos is None else round(cos, 3),
                          "text_before": txt_label in before, "text_after": txt_label in p["top_axes"]})
        results.append({"target": tgt_name, "ok": True, "as_of": r["target"]["as_of"], "peers": peers})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    args = ap.parse_args()
    y = args.year
    floor = float(W._floors_for(y).get("text"))     # ★ 그 연도 벡터공간의 하한(공유=0.52, 프레시=유도)

    avail = W.available_years()
    report = {"year": y, "available_years": avail, "year_servable": y in avail,
              "floor": floor,
              "H2_floor_validity": floor_validity_on_year(y, floor),
              "H3_cj_before_after": cj_before_after(y, floor)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"join_verify_{y}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    # 요약 stdout
    print(json.dumps({"year": y, "servable": report["year_servable"],
                      "available_years": avail,
                      "H2": report["H2_floor_validity"]}, ensure_ascii=False, indent=2))
    for c in report["H3_cj_before_after"]:
        if not c.get("ok"):
            print(f"{c['target']}: not ok ({c.get('reason')})"); continue
        rm = [p for p in c["peers"] if p["text_before"] and not p["text_after"]]
        kp = [p for p in c["peers"] if p["text_before"] and p["text_after"]]
        print(f"\n{c['target']} (as_of {c['as_of']}): "
              f"'사업내용' 제거 {len(rm)}건, 유지 {len(kp)}건")
        for p in rm:
            print(f"  - 제거 {p['peer']}: cos={p['raw_text_cos']} (<{floor})")
        for p in kp:
            print(f"  + 유지 {p['peer']}: cos={p['raw_text_cos']} (≥{floor})")
    print(f"\n→ runs/web10_tag_floor/join_verify_{y}.json", file=sys.stderr)


if __name__ == "__main__":
    main()
