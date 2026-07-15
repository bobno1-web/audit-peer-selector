#!/usr/bin/env python3
"""Loop 4 PART 0 — 임베딩 효과 정찰 (★ 무료: 임베딩/외부 API 호출 0. 캐시된 데이터만).

돈 드는 신경망 임베딩 전에, 그것이 파고들 '틈'이 있는지 공짜로 판정한다.
  0-1 산업코드 해상도: 같은 induty_code 안에서 채점 4비율이 얼마나 이질적인가(eta²).
       eta² 낮음 = 산업코드가 뭉뚱그림 = 텍스트/임베딩이 파고들 틈 큼.
  0-2 텍스트 기여의 성격: L3의 텍스트 축(0.31)이 도운 케이스가 '산업코드 애매(붐비는/이질적)'
       기업에 몰렸나? 몰릴수록 = 임베딩이 더 파고들 여지.
  0-3 오분류 20건: L3 최악 타겟의 peer를 열어 (a)산업코드 오묶음 (b)본질적 특이 (c)데이터 로 분류.

★ 이건 분석(정찰)이다 — 엔진이 아니다. 분석자는 targets 를 봐도 된다(채점기와 같은 지위).
  엔진(SIM)은 여전히 as_of features 만 쓴다. 룩어헤드/누출 아님.
★ text-on peer 는 커밋된 L3 peers.parquet 재사용, text-off 만 새로 랭킹(효율).
"""
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
from pit import as_of                                    # noqa: E402
import score as S                                        # noqa: E402
import run as SIM                                        # noqa: E402

L3 = ROOT / "runs" / "2026-07-15_loop3_similarity"
OUT = ROOT / "runs" / "2026-07-15_loop4_scout"
SECTXT = ROOT / "data" / "pit" / "features" / "business" / "section_text.parquet"
IND = ROOT / "data" / "pit" / "features" / "industry"
MIN_CODE_N = None                                        # 아래서 데이터로 유도(중앙 코드 크기)


def log(m):
    print(m, file=sys.stderr, flush=True)


def dev_years(cfg):
    return [y for y in cfg["pit_split"]["dev_years"]
            if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]


def industry_map(y):
    p = IND / f"industry_{y}.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    return dict(zip(df["corp_code"].astype(str), df["induty_code"].fillna("").astype(str)))


def eta_squared(values, groups):
    """일원분산분석 eta² = 집단간분산/총분산. 산업코드가 그 비율을 설명하는 비율(0~1)."""
    df = pd.DataFrame({"v": values, "g": groups}).dropna()
    df = df[df["g"] != ""]
    if len(df) < 3 or df["g"].nunique() < 2:
        return np.nan
    grand = df["v"].mean()
    ss_tot = ((df["v"] - grand) ** 2).sum()
    if ss_tot <= 0:
        return np.nan
    ss_bet = df.groupby("g")["v"].apply(lambda s: len(s) * (s.mean() - grand) ** 2).sum()
    return float(ss_bet / ss_tot)


def part0_1(cfg, dev, ratios):
    """산업코드 해상도: 코드당 기업수 분포 + 비율별 eta²(코드가 설명하는 분산비율)."""
    rnames = [r["name"] for r in ratios]
    eta = {r: [] for r in rnames}
    size_frac = {"1": 0, "2-5": 0, "6-20": 0, "21+": 0}
    n_firms = 0
    n_codes_list = []
    for y in dev:
        tg = as_of(f"{y}-05-15", with_targets=True).targets
        if not len(tg):
            continue
        tg = tg.set_index("corp_code")
        imap = industry_map(y)
        codes = pd.Series({c: imap.get(str(c), "") for c in tg.index})
        for r in ratios:
            num = pd.to_numeric(tg[r["numerator"]], errors="coerce")
            den = pd.to_numeric(tg[r["denominator"]], errors="coerce")
            val = (num / den).where(den > 0)
            eta[r["name"]].append(eta_squared(val.to_numpy(), codes.reindex(val.index).to_numpy()))
        vc = codes[codes != ""].value_counts()
        n_codes_list.append(vc.size)
        for code, cnt in vc.items():
            n_firms += cnt
            b = "1" if cnt == 1 else "2-5" if cnt <= 5 else "6-20" if cnt <= 20 else "21+"
            size_frac[b] += cnt
    return {
        "eta_squared_by_ratio": {r: round(float(np.nanmean(v)), 4) for r, v in eta.items()},
        "eta_squared_mean": round(float(np.nanmean([np.nanmean(v) for v in eta.values()])), 4),
        "firm_share_by_codesize_pct": {k: round(100 * v / max(n_firms, 1), 1)
                                       for k, v in size_frac.items()},
        "median_codes_per_year": int(np.median(n_codes_list)) if n_codes_list else 0,
        "note": "eta²=산업코드가 설명하는 비율분산의 몫. 낮을수록 코드가 뭉뚱그림(세부축 여지 큼).",
    }


def score_pairs(peers_df, tables, ratios, penalty, min_peers):
    cases = S._cases_from_peers(peers_df, tables, ratios, penalty, min_peers)
    return pd.DataFrame(cases).set_index(["corp_code", "as_of", "ratio"])


def part0_2(cfg, dev, ratios, tables, penalty, min_peers):
    """텍스트 기여가 산업코드 애매(붐빔·이질) 기업에 몰렸나."""
    wj = json.loads((L3 / "weights.json").read_text(encoding="utf-8"))
    order, w = wj["order"], list(wj["weights"])
    ti = order.index("text")
    w_off = list(w)
    w_off[ti] = 0.0
    peers_on = pd.read_parquet(L3 / "peers.parquet")
    txt_idx, txt_mat = SIM.load_text_vectors()
    rows = []
    for y in dev:
        feats = as_of(f"{y}-05-15").features
        if not len(feats):
            continue
        pk = SIM.rank(feats, cfg, w_off, txt_idx, txt_mat, int(cfg["k"]))
        for tgt, plist in pk.items():
            for rr, p in enumerate(plist, 1):
                rows.append({"corp_code": tgt, "as_of": f"{y}-05-15", "rank": rr, "peer_code": p})
    peers_off = pd.DataFrame(rows)
    on = score_pairs(peers_on, tables, ratios, penalty, min_peers)["ape"]
    off = score_pairs(peers_off, tables, ratios, penalty, min_peers)["ape"]
    j = on.index.intersection(off.index)
    help_ = (off.loc[j] - on.loc[j])                     # +면 텍스트가 도움
    # 타겟(코드,연도) 단위 평균 도움 + 산업코드 애매도(그룹 크기)
    per = help_.groupby(level=[0, 1]).mean().rename("text_help").reset_index()
    grp_size, within_het = [], []
    het_by_year = {}
    for y in dev:
        tg = as_of(f"{y}-05-15", with_targets=True).targets
        if not len(tg):
            continue
        tg = tg.set_index("corp_code")
        imap = industry_map(y)
        codes = pd.Series({c: imap.get(str(c), "") for c in tg.index})
        vc = codes[codes != ""].value_counts()
        # 코드별 4비율 평균 within-변동성(그 코드가 얼마나 이질적인가)
        rt = pd.DataFrame(index=tg.index)
        for r in ratios:
            num = pd.to_numeric(tg[r["numerator"]], errors="coerce")
            den = pd.to_numeric(tg[r["denominator"]], errors="coerce")
            rt[r["name"]] = (num / den).where(den > 0)
        het = {}
        for code in vc.index:
            members = codes[codes == code].index
            sub = rt.loc[rt.index.isin(members)]
            iqrs = []
            for r in ratios:
                q75, q25 = sub[r["name"]].quantile(.75), sub[r["name"]].quantile(.25)
                iqrs.append(float(q75 - q25) if pd.notna(q75) and pd.notna(q25) else np.nan)
            het[code] = float(np.nanmean(iqrs)) if any(pd.notna(x) for x in iqrs) else np.nan
        het_by_year[y] = (codes, vc, het)
    for _, rrow in per.iterrows():
        y = int(rrow["as_of"][:4])
        if y not in het_by_year:
            grp_size.append(np.nan); within_het.append(np.nan); continue
        codes, vc, het = het_by_year[y]
        code = codes.get(rrow["corp_code"], "")
        grp_size.append(float(vc.get(code, np.nan)) if code else np.nan)
        within_het.append(het.get(code, np.nan))
    per["code_group_size"] = grp_size
    per["code_within_iqr"] = within_het
    d = per.dropna(subset=["code_group_size"])
    # 붐비는 코드(중앙 초과) vs 희소 코드에서 텍스트 도움 비교
    med = d["code_group_size"].median()
    crowded = d[d["code_group_size"] > med]["text_help"]
    sparse = d[d["code_group_size"] <= med]["text_help"]
    hetd = per.dropna(subset=["code_within_iqr"])
    hmed = hetd["code_within_iqr"].median()
    het_hi = hetd[hetd["code_within_iqr"] > hmed]["text_help"]
    het_lo = hetd[hetd["code_within_iqr"] <= hmed]["text_help"]
    return {
        "text_weight_off_vs_on": {"order": order, "w_on": w, "w_off": w_off},
        "n_targets": int(len(per)),
        "mean_text_help_overall": round(float(per["text_help"].mean()), 4),
        "corr_help_vs_codesize": round(float(d["text_help"].corr(d["code_group_size"])), 3),
        "corr_help_vs_within_iqr": round(float(hetd["text_help"].corr(hetd["code_within_iqr"])), 3),
        "text_help_crowded_codes": round(float(crowded.mean()), 4),
        "text_help_sparse_codes": round(float(sparse.mean()), 4),
        "text_help_heterog_codes": round(float(het_hi.mean()), 4),
        "text_help_homog_codes": round(float(het_lo.mean()), 4),
        "note": "text_help = APE(text off) - APE(text on). +면 텍스트가 예측을 개선.",
    }


def part0_3(cfg, dev, ratios, tables, penalty, min_peers):
    """L3 최악 20 타겟의 peer 열람 근거 추출 (a/b/c 분류용)."""
    sec = pd.read_parquet(SECTXT) if SECTXT.exists() else pd.DataFrame()
    snip = {str(r.corp_code): (str(r.section_text)[:160], str(r.status))
            for r in sec.itertuples()} if len(sec) else {}
    peers_on = pd.read_parquet(L3 / "peers.parquet")
    cases = pd.DataFrame(S._cases_from_peers(peers_on, tables, ratios, penalty, min_peers))
    tgt_ape = cases.groupby(["corp_code", "as_of"])["ape"].mean().sort_values(ascending=False)
    peers_grp = peers_on.groupby(["as_of", "corp_code"])["peer_code"].apply(list)
    txt_idx, txt_mat = SIM.load_text_vectors()
    worst = []
    seen = set()
    for (corp, T), _ in tgt_ape.items():
        if corp in seen:
            continue
        seen.add(corp)
        y = int(T[:4])
        feats = as_of(T).features
        imap = industry_map(y)
        nmap = dict(zip(feats["corp_code"].astype(str), feats.get("corp_name", pd.Series()).astype(str))) \
            if "corp_name" in feats.columns else {}
        plist = peers_on[(peers_on.corp_code == corp) & (peers_on.as_of == T)]["peer_code"].tolist()
        # 타겟-peer 텍스트 코사인
        tcode = str(corp)
        ti = txt_idx.get(tcode)
        def cos(pc):
            a, b = txt_idx.get(tcode), txt_idx.get(str(pc))
            if a is None or b is None or txt_mat is None:
                return None
            return round(float(txt_mat[a] @ txt_mat[b]), 3)
        same_code = sum(1 for p in plist if imap.get(str(p), "x") == imap.get(tcode, "y") and imap.get(tcode))
        cosims = [cos(p) for p in plist]
        cosims_v = [c for c in cosims if c is not None]
        # APE를 주도한 비율의 actual vs peer-중앙값 예측 (근접 0 actual = APE폭발 진단)
        rt = tables.get(T)
        driver = None
        if rt is not None and corp in rt.index:
            plist2 = peers_grp.get((T, corp), [])
            best = None
            for r in ratios:
                actual = rt.at[corp, r["name"]]
                if pd.isna(actual) or actual == 0:
                    continue
                pv = [rt.at[p, r["name"]] for p in plist2
                      if p in rt.index and not pd.isna(rt.at[p, r["name"]])]
                if len(pv) >= min_peers:
                    pred = float(np.median(pv)); ape = abs(pred - actual) / abs(actual)
                else:
                    pred, ape = None, penalty
                if best is None or ape > best[1]:
                    best = (r["name"], float(ape), float(actual), pred)
            if best:
                driver = {"ratio": best[0], "ape": round(best[1], 2),
                          "actual": round(best[2], 4),
                          "pred": round(best[3], 4) if best[3] is not None else None}
        rec = {
            "corp_code": corp, "as_of": T, "mean_ape": round(float(tgt_ape[(corp, T)]), 3),
            "induty": imap.get(tcode, ""), "name": nmap.get(tcode, ""),
            "sec_status": snip.get(tcode, ("", "missing"))[1],
            "sec_snip": snip.get(tcode, ("", ""))[0],
            "driver": driver,
            "peers_same_induty": int(same_code),
            "peer_text_cos_mean": round(float(np.mean(cosims_v)), 3) if cosims_v else None,
            "peers": [{"code": str(p), "name": nmap.get(str(p), ""),
                       "induty": imap.get(str(p), ""), "text_cos": cos(p),
                       "snip": snip.get(str(p), ("", ""))[0][:80]} for p in plist],
        }
        rec["cause"] = _classify(rec)
        worst.append(rec)
        if len(worst) >= 20:
            break
    return worst


def _classify(rec):
    """(a)산업코드 오묶음 → 텍스트/임베딩 여지 / (b)본질적 특이 → 어떤 축도 못 고침 / (c)데이터.
    신호: sec_status(텍스트 결측=c), driver(비율 actual 근접0=APE폭발=b),
    peer 응집도(같은코드수·텍스트코사인 낮음=산업코드가 못 묶음=a)."""
    d = rec.get("driver")
    if rec["sec_status"] != "ok" or d is None:
        return "c_data"                                   # 텍스트 결측/정의불가 → 축 적용 불가
    # APE 폭발: |actual| 이 아주 작아 상대오차가 폭발 (어떤 peer도 못 맞춤)
    if d["ape"] >= 3.0 and abs(d["actual"]) < 0.05:
        return "b_intrinsic"
    coherent = (rec["peers_same_induty"] >= 3) or ((rec["peer_text_cos_mean"] or 0) >= 0.35)
    if d["ape"] >= 3.0 and coherent:
        return "b_intrinsic"                              # 좋은 peer인데도 큰 오차 → 특이
    if not coherent:
        return "a_industry_lump"                          # peer 흩어짐 → 더 나은 텍스트 여지
    return "b_intrinsic"


def main():
    cfg = S.load_cfg()
    ratios = cfg["ratios"]
    dev = dev_years(cfg)
    q = float(cfg["penalty"]["quantile"])
    min_peers = int(cfg["min_valid_peers"])
    tables, markets = S.ratio_tables(dev, ratios)
    penalty = S.derive_penalty(S._cases_from_market(tables, markets, ratios), q)
    log(f"dev={dev} penalty={penalty:.4f}")

    r01 = part0_1(cfg, dev, ratios)
    log(f"[0-1] eta²(mean)={r01['eta_squared_mean']}  by_ratio={r01['eta_squared_by_ratio']}")
    r02 = part0_2(cfg, dev, ratios, tables, penalty, min_peers)
    log(f"[0-2] corr(help,codesize)={r02['corr_help_vs_codesize']} "
        f"crowded={r02['text_help_crowded_codes']} sparse={r02['text_help_sparse_codes']}")
    r03 = part0_3(cfg, dev, ratios, tables, penalty, min_peers)
    from collections import Counter
    causes = Counter(c["cause"] for c in r03)
    log(f"[0-3] worst {len(r03)} 타겟; 원인 분류 {dict(causes)}")

    OUT.mkdir(parents=True, exist_ok=True)
    out = {"api_calls": 0, "part0_1_industry_resolution": r01,
           "part0_2_text_character": r02,
           "part0_3_cause_counts": dict(causes), "part0_3_worst_cases": r03}
    (OUT / "scout.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"scout → {OUT}/scout.json  (api_calls=0)")


if __name__ == "__main__":
    main()
