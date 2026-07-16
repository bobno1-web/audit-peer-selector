#!/usr/bin/env python3
"""Loop 6 PART 1(예측방식 B) + PART 2(예측불가 분리 C) — dev 전용.

B: L4 peer 선정을 고정하고 '집계 방식'만 바꿔 dev APE 를 비교한다.
   (a) median(ORACLE 동결 기본=대조군) (b) 유사도 가중평균 (c) 유사도 가중중앙값 (d) 절사평균
   (e) k∈{3,5,7,10}. 최선 변형 식별. ★ median 경로가 canonical(score.py)과 동일함을 검증(자기검증).
C: 구조적 예측불가(ill-conditioned) 케이스 플래그 = s=|비율분자|/총자산 < τ_r(dev 하위분위수, D-027).
   (전체) 모든 케이스 / (안정) 플래그 제외 두 APE 를 시장·L4·최선변형에 대해 보고. 제외비율 명시.

★ 정보 차단벽: 예측은 peer 의 채점비율 값 + 엔진 유사도점수만(타겟 비율 미접근). C 플래그는 타겟
  '재무구조'(분자계정·총자산)로만(채점비율 실제값 미사용). engines↛scoring 유지(이 스크립트는 채점측).
★ dev(2016~2022)만. holdout 미사용. 상수(q_sep·penalty·k)는 config·dev 유도.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
from pit import as_of                                       # noqa: E402
from scoring.oracle import score as SC                      # noqa: E402
import run as SIM                                           # noqa: E402  (similarity 엔진)

RUN = ROOT / "runs" / "2026-07-16_loop6"
L4 = ROOT / "runs" / "2026-07-15_loop4_similarity"
L4_ORDER = ["industry", "scale", "mktcap", "text", "growth"]


def dev_Ts(cfg):
    sd = ROOT / "data" / "pit" / "features" / "scale"
    ys = [y for y in cfg["pit_split"]["dev_years"] if (sd / f"scale_{y}.parquet").exists()]
    return ys, [f"{y}-05-15" for y in ys]


# ---------- 집계 방식(B) ----------
def agg_median(vals, sims):
    return float(np.median(vals))


def agg_wmean(vals, sims):
    w = np.asarray(sims, dtype=float)
    if w.sum() <= 0:
        return float(np.mean(vals))
    return float(np.average(vals, weights=w))


def agg_wmedian(vals, sims):
    v = np.asarray(vals, dtype=float)
    w = np.asarray(sims, dtype=float)
    if w.sum() <= 0:
        return float(np.median(v))
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w)
    idx = int(np.searchsorted(cw, 0.5 * cw[-1], side="left"))
    return float(v[min(idx, len(v) - 1)])


def agg_trimmed(vals, sims):
    v = np.sort(np.asarray(vals, dtype=float))
    if len(v) >= 3:
        v = v[1:-1]                                         # 최소·최대 1개씩 절사
    return float(np.mean(v))


AGG = {"median": agg_median, "weighted_mean": agg_wmean,
       "weighted_median": agg_wmedian, "trimmed_mean": agg_trimmed}


# ---------- peer 선정(L4 고정) + 유사도 ----------
def l4_peers_with_sim(cfg, Ts, kmax):
    """L4 가중치·5축으로 각 타겟 top-kmax peer + 유사도점수. {T:{corp:[(peer,sim)...]}}."""
    cfg_l4 = deepcopy(cfg)
    cfg_l4["similarity"]["components"] = L4_ORDER
    w = json.loads((L4 / "weights.json").read_text(encoding="utf-8"))["weights"]
    txt_idx, txt_mat = SIM.load_text_vectors()
    out = {}
    for T, y in zip(Ts, [int(t[:4]) for t in Ts]):
        feats = as_of(T).features
        if not len(feats):
            continue
        pk = SIM.rank(feats, cfg_l4, w, txt_idx, txt_mat, kmax, with_sim=True)
        out[T] = pk
    return out


def verify_selection(peers_sim, k):
    """생성한 top-k peer 코드집합이 커밋된 L4 peers.parquet 과 동일한지(선정 재현 검증)."""
    ref = pd.read_parquet(L4 / "peers.parquet")
    ref = ref[ref["rank"] <= k]
    refset = ref.groupby(["as_of", "corp_code"])["peer_code"].apply(lambda s: tuple(s)).to_dict()
    mism = 0
    for T, pm in peers_sim.items():
        for corp, plist in pm.items():
            got = tuple(p for p, _ in plist[:k])
            want = refset.get((T, corp))
            if want is not None and got != want:
                mism += 1
    return mism


# ---------- 채점(집계 방식 파라미터화; frozen 평가는 그대로) ----------
def cases_predict(peers_sim, tables, ratios, penalty, min_peers, agg, k):
    cases = []
    for T, pm in peers_sim.items():
        rt = tables.get(T)
        if rt is None:
            continue
        for corp, plist in pm.items():
            if corp not in rt.index:
                continue
            pk = plist[:k]
            for r in ratios:
                actual = rt.at[corp, r["name"]]
                if pd.isna(actual) or actual == 0:
                    continue
                vals, sims = [], []
                for p, s in pk:
                    if p in rt.index and not pd.isna(rt.at[p, r["name"]]):
                        vals.append(rt.at[p, r["name"]])
                        sims.append(s)
                if len(vals) >= min_peers:
                    ape = abs(agg(vals, sims) - actual) / abs(actual)
                    fail = False
                else:
                    ape, fail = penalty, True
                cases.append({"corp_code": corp, "as_of": T, "ratio": r["name"],
                              "ape": float(ape), "fail": fail})
    return cases


def median_ape(cases):
    return float(np.median([c["ape"] for c in cases])) if cases else float("nan")


# ---------- 예측불가 분리(C) ----------
def separation(Ts, ratios, q):
    """각 비율 r 에 대해 s=|분자계정|/총자산 의 dev 하위 q 분위수 τ_r. flag = {(T,corp,ratio)}.
    반환 (flag_set, tau_by_ratio, coverage_note)."""
    num_by_ratio = {r["name"]: r["numerator"] for r in ratios}
    s_vals = {r["name"]: [] for r in ratios}
    per_case_s = {}                                          # (T,corp,ratio)->s
    for T in Ts:
        tg = as_of(T, with_targets=True).targets
        ft = as_of(T).features
        if not len(tg) or not len(ft) or "총자산" not in ft.columns:
            continue
        tg = tg.set_index("corp_code")
        ta = ft.set_index("corp_code")["총자산"]
        for r in ratios:
            name = r["name"]
            num = pd.to_numeric(tg[num_by_ratio[name]], errors="coerce")
            den = pd.to_numeric(tg[r["denominator"]], errors="coerce")
            defined = num.notna() & den.notna() & (den > 0)  # 채점되는 케이스만
            for corp in tg.index[defined]:
                assets = ta.get(corp)
                if assets is None or pd.isna(assets) or assets <= 0:
                    continue                                 # 총자산 결측 → 플래그 안 함
                s = abs(float(num[corp])) / float(assets)
                s_vals[name].append(s)
                per_case_s[(T, corp, name)] = s
    tau = {name: (float(np.quantile(v, q)) if v else float("nan")) for name, v in s_vals.items()}
    flag = {key for key, s in per_case_s.items() if not np.isnan(tau[key[2]]) and s < tau[key[2]]}
    return flag, tau, {name: len(v) for name, v in s_vals.items()}


def split_report(cases, flag):
    """(전체 median, 안정 median, 제외비율, n_전체, n_제외)."""
    keyed = [(c, (c["as_of"], c["corp_code"], c["ratio"]) in flag) for c in cases]
    all_ape = [c["ape"] for c, _ in keyed]
    stable = [c["ape"] for c, f in keyed if not f]
    n = len(all_ape)
    n_excl = n - len(stable)
    return {"overall_median": float(np.median(all_ape)) if all_ape else float("nan"),
            "stable_median": float(np.median(stable)) if stable else float("nan"),
            "excl_rate": round(n_excl / n, 4) if n else 0.0,
            "n_total": n, "n_excluded": n_excl}


def main():
    cfg = SC.load_cfg()
    ratios = cfg["ratios"]
    min_peers = int(cfg["min_valid_peers"])
    K = int(cfg["k"])
    q_sep = float(cfg["separation"]["numerator_over_assets_quantile"])
    ys, Ts = dev_Ts(cfg)
    tables, markets = SC.ratio_tables(ys, ratios)
    penalty = SC.derive_penalty(SC._cases_from_market(tables, markets, ratios),
                                cfg["penalty"]["quantile"])

    kmax = max(cfg["prediction"]["k_grid"] + [K])
    peers_sim = l4_peers_with_sim(cfg, Ts, kmax)
    mism = verify_selection(peers_sim, K)

    # ★ 자기검증: median 경로가 canonical(score.py)과 동일한가
    canon = SC._cases_from_peers(pd.read_parquet(L4 / "peers.parquet"),
                                 tables, ratios, penalty, min_peers)
    canon_med = median_ape(canon)
    mine_med = median_ape(cases_predict(peers_sim, tables, ratios, penalty, min_peers,
                                        AGG["median"], K))
    verify_ok = abs(canon_med - mine_med) < 1e-9

    # B: 방식 격자(k=K 고정) + k 격자(median 고정)
    method_res = {}
    for m in cfg["prediction"]["methods_grid"]:
        c = cases_predict(peers_sim, tables, ratios, penalty, min_peers, AGG[m], K)
        method_res[m] = {"ape_median": round(median_ape(c), 4),
                         "per_ratio": {r["name"]: round(median_ape(
                             [x for x in c if x["ratio"] == r["name"]]), 4) for r in ratios}}
    k_res = {}
    for kk in cfg["prediction"]["k_grid"]:
        c = cases_predict(peers_sim, tables, ratios, penalty, min_peers, AGG["median"], kk)
        k_res[str(kk)] = round(median_ape(c), 4)

    # 최선 변형(방식×k 전조합; dev APE median 최소)
    best = None
    combo = {}
    for m in cfg["prediction"]["methods_grid"]:
        for kk in cfg["prediction"]["k_grid"]:
            c = cases_predict(peers_sim, tables, ratios, penalty, min_peers, AGG[m], kk)
            v = round(median_ape(c), 4)
            combo[f"{m}@k{kk}"] = v
            if best is None or v < best[2]:
                best = (m, kk, v)
    best_method, best_k, best_ape = best

    # C: 분리 (시장·L4-median·최선변형)
    flag, tau, s_counts = separation(Ts, ratios, q_sep)
    market_cases = SC._cases_from_market(tables, markets, ratios)
    l4_cases = cases_predict(peers_sim, tables, ratios, penalty, min_peers, AGG["median"], K)
    best_cases = cases_predict(peers_sim, tables, ratios, penalty, min_peers,
                               AGG[best_method], best_k)
    sep = {"tau_by_ratio": {k2: round(v, 6) for k2, v in tau.items()},
           "q_sep": q_sep, "n_flagged_cases": len(flag),
           "market": split_report(market_cases, flag),
           "L4_median": split_report(l4_cases, flag),
           "best_variant": split_report(best_cases, flag)}

    out = {"dev_years": ys, "penalty": round(penalty, 4), "k": K,
           "selection_mismatch_vs_committed_L4": mism,
           "verify_median_eq_canonical": {"canonical": round(canon_med, 6),
                                          "mine": round(mine_med, 6), "ok": verify_ok},
           "B_methods_k5": method_res, "B_k_median": k_res, "B_all_combos": combo,
           "B_best": {"method": best_method, "k": best_k, "ape_median": best_ape},
           "C_separation": sep}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "predict_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
