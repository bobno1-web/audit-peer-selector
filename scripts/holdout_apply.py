#!/usr/bin/env python3
"""holdout 개봉·적용 (Loop 7 PART 1) — ★ dev 동결 설정을 그대로 적용만. 재학습 0.

freeze(config/holdout_freeze.json)에서 **모든 튜닝 상수**(엔진별 weights·k, penalty, τ_r)를 읽어 dev·
holdout 을 **동일 하네스**로 채점한다. penalty·τ_r 을 holdout 에서 재유도하지 않는다(동결값 사용).
개봉 전후 freeze SHA-256 불변을 검증(튜닝 안 함 증거). 결과에 provenance 지문 스탬프.
"""
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scoring" / "oracle"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))    # 'run' = similarity 엔진
from pit import as_of                                       # noqa: E402
import score as S                                           # noqa: E402
import run as SIM                                           # noqa: E402  (similarity)
import provenance as PV                                     # noqa: E402
import engines.baseline.run as BASE                         # noqa: E402  (패키지 경로 — 충돌 회피)

FREEZE = ROOT / "config" / "holdout_freeze.json"
FREEZE_HASH = ROOT / "config" / "holdout_freeze.sha256"
RUN = ROOT / "runs" / "2026-07-16_loop7"
SEED = 20260715
NB = 2000
DEV = list(range(2016, 2023))
HOLD = list(range(2023, 2026))


def verify_freeze():
    body = FREEZE.read_text(encoding="utf-8")
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    want = FREEZE_HASH.read_text(encoding="utf-8").strip()
    assert h == want, f"[FREEZE] 해시 불일치 — 개봉 후 freeze 변경(부정)! {h} != {want}"
    return json.loads(body), h


def flags_from_tau(Ts, ratios, tau):
    """★ 동결 τ_r(dev)로 holdout/dev 케이스 플래그. holdout 재유도 아님."""
    flag = set()
    for T in Ts:
        tg = as_of(T, with_targets=True).targets
        ft = as_of(T).features
        if not len(tg) or not len(ft) or "총자산" not in ft.columns:
            continue
        tg = tg.set_index("corp_code")
        assets = ft.set_index("corp_code")["총자산"]
        for r in ratios:
            num = pd.to_numeric(tg[r["numerator"]], errors="coerce")
            den = pd.to_numeric(tg[r["denominator"]], errors="coerce")
            defined = num.notna() & den.notna() & (den > 0)
            trr = tau[r["name"]]
            for corp in tg.index[defined]:
                a = assets.get(corp)
                if a is None or pd.isna(a) or a <= 0:
                    continue
                if abs(float(num[corp])) / float(a) < trr:
                    flag.add((T, corp, r["name"]))
    return flag


def engine_peers(spec, years, base_cfg, txt_idx, txt_mat):
    rows = []
    for y in years:
        T = f"{y}-05-15"
        feats = as_of(T).features
        if not len(feats):
            continue
        if spec["type"] == "baseline":
            cfg_b = copy.deepcopy(base_cfg); cfg_b["k"] = spec["k"]
            pk = BASE.rank_peers(feats, cfg_b)
        else:
            cfg_e = copy.deepcopy(base_cfg)
            cfg_e["similarity"]["components"] = spec["components"]
            pk = SIM.rank(feats, cfg_e, spec["weights"], txt_idx, txt_mat, spec["k"])
        for tgt, plist in pk.items():
            for r, p in enumerate(plist, 1):
                rows.append({"corp_code": tgt, "as_of": T, "rank": r, "peer_code": p})
    return pd.DataFrame(rows)


def split_report(cases, flag):
    allape = [c["ape"] for c in cases]
    stable = [c["ape"] for c in cases if (c["as_of"], c["corp_code"], c["ratio"]) not in flag]
    n = len(allape)
    return {"overall": round(float(np.median(allape)), 4) if allape else None,
            "stable": round(float(np.median(stable)), 4) if stable else None,
            "excl_rate": round((n - len(stable)) / n, 4) if n else 0.0,
            "coverage": round(float(np.mean([not c["fail"] for c in cases])), 4) if cases else 0.0,
            "per_ratio": {r: round(float(np.median([c["ape"] for c in cases if c["ratio"] == r])), 4)
                          for r in {c["ratio"] for c in cases}},
            "within": {w: round(float(np.mean([c["ape"] <= w / 100 for c in cases])), 4)
                       for w in (10, 20, 30)}}


def to_series(cases):
    return pd.DataFrame(cases).set_index(["corp_code", "as_of", "ratio"])["ape"]


def boot(a, b, rng, cluster):
    j = a.index.intersection(b.index)
    av, bv = a.loc[j].to_numpy(), b.loc[j].to_numpy()
    if cluster:
        corps = np.array([i[0] for i in j]); uniq = np.array(sorted(set(corps)))
        by = {c: np.where(corps == c)[0] for c in uniq}; nC = len(uniq)
        d = np.array([np.median(bv[np.concatenate([by[c] for c in uniq[rng.integers(0, nC, nC)]])])
                      - np.median(av[np.concatenate([by[c] for c in uniq[rng.integers(0, nC, nC)]])])
                      for _ in range(NB)])
    else:
        n = len(j)
        d = np.array([np.median(bv[idx]) - np.median(av[idx])
                      for idx in (rng.integers(0, n, n) for _ in range(NB))])
    return {"point": round(float(np.median(bv) - np.median(av)), 4),
            "ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)],
            "significant": bool(np.percentile(d, 97.5) < 0)}


def score_split(years, Ts, engines, ratios, penalty, min_peers, tau, base_cfg, txt):
    tables, markets = S.ratio_tables(years, ratios)
    flag = flags_from_tau(Ts, ratios, tau)
    rep, series = {}, {}
    for name, spec in engines.items():
        peers = engine_peers(spec, years, base_cfg, txt[0], txt[1])
        cases = S._cases_from_peers(peers, tables, ratios, penalty, min_peers)
        rep[name] = split_report(cases, flag)
        series[name] = to_series(cases)
    return rep, series


def main():
    freeze, fhash = verify_freeze()
    ratios = freeze["ratios"]
    penalty = float(freeze["penalty_ape"])
    tau = freeze["separation"]["tau_by_ratio"]
    min_peers = int(freeze["min_valid_peers"])
    engines = freeze["engines"]
    base_cfg = S.load_cfg()
    txt = SIM.load_text_vectors()

    dev_rep, _ = score_split(DEV, [f"{y}-05-15" for y in DEV], engines, ratios, penalty,
                             min_peers, tau, base_cfg, txt)
    hold_rep, hold_series = score_split(HOLD, [f"{y}-05-15" for y in HOLD], engines, ratios,
                                        penalty, min_peers, tau, base_cfg, txt)

    rng = np.random.default_rng(SEED)
    l6, base, l4 = hold_series["similarity_L6"], hold_series["baseline"], hold_series["similarity_L4"]
    bootres = {
        "L6_vs_baseline_paired": boot(base, l6, rng, False),
        "L6_vs_baseline_clustered": boot(base, l6, rng, True),
        "L6_vs_L4_paired": boot(l4, l6, rng, False),
        "L6_vs_L4_clustered": boot(l4, l6, rng, True),
    }
    freeze2_hash = hashlib.sha256(FREEZE.read_text(encoding="utf-8").encode()).hexdigest()
    out = {"freeze_sha256": fhash, "freeze_unchanged_after_open": freeze2_hash == fhash,
           "dev_targets_digest": PV.combined_targets_digest(DEV),
           "holdout_targets_digest": PV.combined_targets_digest(HOLD),
           "dev": dev_rep, "holdout": hold_rep, "holdout_bootstrap": bootres,
           "win_condition": 0.433}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "holdout_scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(json.dumps({"freeze_unchanged": out["freeze_unchanged_after_open"],
                      "engines": {n: {"dev": dev_rep[n]["overall"], "hold": hold_rep[n]["overall"]}
                                  for n in engines}, "boot": bootres}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
