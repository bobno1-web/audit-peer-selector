#!/usr/bin/env python3
"""산출물 정교화 (Loop 8 PART 1) — 검증된 L6 엔진 위의 '표현 계층'. ★ 예측오차 미변경.

엔진(peer 선정)·채점기(APE)를 **건드리지 않고**, 그 출력을 감사 실무에 쓰기 좋게 정교화한다:
  1) peer 신뢰도 등급(HIGH/MEDIUM/LOW): peer 응집도(top-k 유사도 평균)의 dev 분포 삼분위. ★ 채점비율
     실제값 미사용(정답 훔쳐보기 금지) — 유사도(엔진)·유효peer수(정의여부)·예측불가(구조)만.
  2) 선정 근거: 각 peer 의 축별 유사도 기여(w_c·sim_c) — "왜 이 회사가 peer 인가".
  3) 확인필요지점: 타겟이 peer 중앙값 대비 크게 벗어난 비율(채점기가 이미 계산한 편차 재활용).
  4) 구조화 출력(JSON/CSV) — OUTPUT_FORMAT.md 스키마.
상수(삼분위·편차분위)는 config·dev 유도. dev 기업만(holdout 미사용).
"""
import copy
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
from pit import as_of                                       # noqa: E402
import score as S                                           # noqa: E402
import run as SIM                                           # noqa: E402
import loop6_predict as LP                                  # noqa: E402

RUN = ROOT / "runs" / "2026-07-16_loop8"
L4 = ROOT / "runs" / "2026-07-15_loop4_similarity"
L4_ORDER = ["industry", "scale", "mktcap", "text", "growth"]


def l6_cfg_weights(cfg):
    c = copy.deepcopy(cfg)
    c["similarity"]["components"] = L4_ORDER
    w = json.loads((L4 / "weights.json").read_text(encoding="utf-8"))["weights"]
    w = np.array(w, float); w = w / w.sum()
    return c, w


def year_engine(year, cfg_l6, txt):
    """그 해 스냅샷의 축별 유사도 기저 + 코드. (엔진 허용 피처만.)"""
    feats = as_of(f"{year}-05-15").features
    A = SIM.year_arrays(feats, cfg_l6, txt[0], txt[1])
    return feats, A


def target_report(A, w, i, k, comps, rt, tg_raw, assets, tau, min_peers):
    """한 타겟의 정교화 리포트(peer 근거·신뢰등급·확인필요지점). rt=비율표, tg_raw=원계정, assets=총자산."""
    codes = A["codes"]
    axis = {c: SIM.SIMS[c](A, i) for c in comps}            # 축별 유사도 벡터
    total = sum(w[ci] * axis[c] for ci, c in enumerate(comps))
    total[i] = -np.inf
    order = np.argsort(total)[::-1][:k]
    peer_sims = [float(total[j]) for j in order]
    cohesion = float(np.mean(peer_sims)) if peer_sims else 0.0
    peers = []
    for j in order:
        peers.append({"rank": len(peers) + 1, "peer_code": str(codes[j]),
                      "similarity": round(float(total[j]), 4),
                      "rationale": {c: round(float(w[ci] * axis[c][j]), 4)
                                    for ci, c in enumerate(comps)}})
    return cohesion, peers, order


def grade(cohesion, thr):
    return "HIGH" if cohesion >= thr["q67"] else ("MEDIUM" if cohesion >= thr["q33"] else "LOW")


def derive_thresholds(dev, cfg, w, k, txt, ratios, q_cohesion, q_dev):
    """dev 에서 응집도 삼분위 + 편차 상위 분위수 유도(임의상수 아님)."""
    cohs, devs = [], []
    tables, _ = S.ratio_tables(dev, ratios)
    for y in dev:
        feats, A = year_engine(y, cfg, txt)
        codes = A["codes"]
        rt = tables.get(f"{y}-05-15")
        comps = L4_ORDER
        for i in range(len(codes)):
            axis = {c: SIM.SIMS[c](A, i) for c in comps}
            total = sum(w[ci] * axis[c] for ci, c in enumerate(comps))
            total[i] = -np.inf
            order = np.argsort(total)[::-1][:k]
            cohs.append(float(np.mean([total[j] for j in order])))
            if rt is None or str(codes[i]) not in rt.index:
                continue
            for r in ratios:
                actual = rt.at[str(codes[i]), r["name"]]
                if pd.isna(actual) or actual == 0:
                    continue
                pv = [rt.at[str(codes[j]), r["name"]] for j in order
                      if str(codes[j]) in rt.index and not pd.isna(rt.at[str(codes[j]), r["name"]])]
                if len(pv) >= 3:
                    devs.append(abs(np.median(pv) - actual) / abs(actual))
    return {"q33": float(np.quantile(cohs, q_cohesion[0])),
            "q67": float(np.quantile(cohs, q_cohesion[1])),
            "dev_flag": float(np.quantile(devs, q_dev))}


def build_ratio_block(order, codes, i, rt, tg_raw, assets, ratios, tau, min_peers, dev_flag, peer_grade):
    out = []
    for r in ratios:
        name, num_acct = r["name"], r["numerator"]
        actual = rt.at[str(codes[i]), name] if str(codes[i]) in rt.index else np.nan
        if pd.isna(actual) or actual == 0:
            continue
        pv = [rt.at[str(codes[j]), name] for j in order
              if str(codes[j]) in rt.index and not pd.isna(rt.at[str(codes[j]), name])]
        valid = len(pv)
        # 예측불가(구조): |분자|/총자산 < τ_r
        ill = False
        a = assets.get(str(codes[i]))
        nv = pd.to_numeric(pd.Series([tg_raw.at[str(codes[i]), num_acct]]), errors="coerce").iloc[0] \
            if str(codes[i]) in tg_raw.index else np.nan
        if a is not None and not pd.isna(a) and a > 0 and not pd.isna(nv):
            ill = bool(abs(float(nv)) / float(a) < tau[name])
        if valid >= min_peers:
            pm = float(np.median(pv))
            dev = abs(pm - actual) / abs(actual)
            check = bool(dev >= dev_flag)                   # 확인필요지점(채점기 편차 재활용)
            direction = "상위" if actual > pm else "하위"
            r_grade = "LOW" if (ill or valid < min_peers) else peer_grade
            out.append({"ratio": name, "peer_median": round(pm, 4), "target_actual": round(float(actual), 4),
                        "deviation_pct": round(100 * dev, 1), "direction": direction,
                        "check_needed": check, "confidence": r_grade,
                        "valid_peers": valid, "comparable": (not ill),
                        "note": "비교 부적합(손익분기 근처)" if ill else ""})
        else:
            out.append({"ratio": name, "peer_median": None, "target_actual": round(float(actual), 4),
                        "deviation_pct": None, "confidence": "LOW", "valid_peers": valid,
                        "comparable": (not ill), "note": "유효 peer<3(예측 신뢰 낮음)"})
    return out


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    k = int(cfg["prediction"]["k"])
    min_peers = int(cfg["min_valid_peers"])
    q_sep = float(cfg["separation"]["numerator_over_assets_quantile"])
    rc = cfg["report"]
    cfg_l6, w = l6_cfg_weights(cfg)
    txt = SIM.load_text_vectors()
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]

    thr = derive_thresholds(dev, cfg_l6, w, k, txt, ratios, rc["cohesion_quantiles"],
                            rc["deviation_flag_quantile"])
    _, tau, _ = LP.separation([f"{y}-05-15" for y in dev], ratios, q_sep)

    # 예시 연도(가장 최근 dev)에서 리포트 생성
    year = max(dev)
    T = f"{year}-05-15"
    tables, _ = S.ratio_tables([year], ratios)
    rt = tables[T]
    tg_raw = as_of(T, with_targets=True).targets.set_index("corp_code")
    ft = as_of(T).features
    assets = ft.set_index("corp_code")["총자산"] if "총자산" in ft.columns else pd.Series(dtype=float)
    _, A = year_engine(year, cfg_l6, txt)
    codes = A["codes"]

    reports = []
    for i in range(len(codes)):
        coh, peers, order = target_report(A, w, i, k, L4_ORDER, rt, tg_raw, assets, tau, min_peers)
        pg = grade(coh, thr)
        ratio_block = build_ratio_block(order, codes, i, rt, tg_raw, assets, ratios, tau,
                                        min_peers, thr["dev_flag"], pg)
        reports.append({"target": str(codes[i]), "as_of": T, "peer_confidence": pg,
                        "peer_cohesion": round(coh, 4), "peers": peers, "ratios": ratio_block})

    # 예시 선정(하드코딩 아님 — 기준으로): HIGH/MEDIUM/LOW 각 1 + 확인필요지점 1
    def pick(pred):
        for r in reports:
            if pred(r):
                return r
        return None
    examples = {
        "HIGH_confidence": pick(lambda r: r["peer_confidence"] == "HIGH" and r["ratios"]),
        "MEDIUM_confidence": pick(lambda r: r["peer_confidence"] == "MEDIUM" and r["ratios"]),
        "LOW_confidence": pick(lambda r: r["peer_confidence"] == "LOW" and r["ratios"]),
        "check_needed_example": pick(lambda r: any(x.get("check_needed") for x in r["ratios"])),
        "not_comparable_example": pick(lambda r: any(not x["comparable"] for x in r["ratios"])),
    }

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "thresholds.json").write_text(json.dumps(
        {"thresholds": {k2: round(v, 6) for k2, v in thr.items()}, "config": rc,
         "derived_from": "dev", "note": "응집도 삼분위·편차 상위분위수 — dev 유도(임의상수 아님)"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN / "sample_reports.json").write_text(json.dumps(
        {"as_of": T, "engine": "similarity_l6", "n_targets": len(reports),
         "thresholds": {k2: round(v, 6) for k2, v in thr.items()}, "examples": examples},
        ensure_ascii=False, indent=2), encoding="utf-8")
    # 범용 CSV(기업코드·순위·유사도·신뢰등급·근거)
    with open(RUN / "peer_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        wri = csv.writer(f)
        wri.writerow(["target", "as_of", "peer_confidence", "peer_cohesion", "rank", "peer_code",
                      "similarity"] + [f"why_{c}" for c in L4_ORDER])
        for r in reports:
            for p in r["peers"]:
                wri.writerow([r["target"], r["as_of"], r["peer_confidence"], r["peer_cohesion"],
                              p["rank"], p["peer_code"], p["similarity"]]
                             + [p["rationale"][c] for c in L4_ORDER])

    # ★ T7: 엔진 점수 불변 확인(정교화는 표현 계층 — 엔진/채점기 미변경)
    peers_l6 = pd.read_parquet(ROOT / "runs" / "2026-07-16_loop6" / "peers.parquet")
    tb, mk = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tb, mk, ratios), float(cfg["penalty"]["quantile"]))
    l6_score = float(pd.DataFrame(S._cases_from_peers(peers_l6, tb, ratios, penalty, min_peers))["ape"].median())
    print(json.dumps({"n_targets": len(reports), "thresholds": {k2: round(v, 4) for k2, v in thr.items()},
                      "example_grades": {k2: (v["peer_confidence"] if v else None) for k2, v in examples.items()},
                      "engine_score_unchanged": {"L6_dev_ape": round(l6_score, 4), "expected": 0.4794,
                                                 "unchanged": round(l6_score, 4) == 0.4794}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
