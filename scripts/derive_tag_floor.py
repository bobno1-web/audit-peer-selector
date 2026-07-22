#!/usr/bin/env python3
"""태그 절대하한(사업내용) 도출·검증 — WEB-10 ①. ★ 표시 계층 전용. 엔진/채점기/순위 불변.

문제: 태그 로직이 rationale 상위 2축(v>0)이면 라벨을 붙인다. 텍스트(사업내용) 축은
  사업보고서 상투어("제조·판매·사업의 내용"…) 겹침만으로도 무관 산업 쌍의 코사인이 0 근처로
  안 죽어(널 p50≈0.18), 식품↔전선 같은 오판정이 "사업내용 유사"로 붙는다.

하한 도출(데이터 유도, 하드코딩 금지):
  - 널(null) 정의 = KSIC 2자리(대분류)가 서로 다른 회사 쌍 = 사업이 무관한 쌍.
    이들의 텍스트 코사인은 상투어 겹침만 반영한다.
  - 하한 = 널 분포의 p99. "무관 산업 쌍이 상투어만으로 우연히 도달하는 수준을 1% 이내로
    초과" = 통계적으로 유의한 실제 텍스트 겹침. (분위수 q 는 config, 값은 데이터에서.)
  - dev 연도(2016-2022)만 사용(holdout 봉인). 연도별 p99 안정성으로 타 시점 타당성 확인.

판별력(하한이 실제 산업일치와 상관되는지):
  - 같은-KSIC2 쌍 vs 다른-KSIC2 쌍 코사인의 AUC(=P(같은>다른)). 0.5=무판별, 1.0=완전판별.

★ 재현: 이 스크립트가 config/tag_thresholds.json 의 도출 근거다(no-false-provenance).
  `python scripts/derive_tag_floor.py` → runs/web10_tag_floor/derivation.json + stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))
from pit import as_of                                    # noqa: E402
import run as SIM                                        # noqa: E402

CONFIG = ROOT / "config" / "default.yaml"
OUT = ROOT / "runs" / "web10_tag_floor"
KSIC_PREFIX = 2          # 대분류(2자리) = "무관 산업" 판단 단위(구조적; 종목·회사 리터럴 아님)
QUANTILE = 0.99          # 널 분포 하한 분위수(값이 아니라 방법을 고정)


def _year_vectors(year: int, txt_idx, txt_mat):
    """as_of(year) 유니버스에서 (텍스트벡터 & KSIC 보유) 기업의 행렬·산업2자리 반환."""
    feats = as_of(f"{year}-05-15").features
    if not len(feats) or txt_mat is None:
        return None, None
    codes = feats["corp_code"].astype(str).to_numpy()
    induty = feats["induty_code"].fillna("").astype(str).to_numpy()
    rows, ind2 = [], []
    for c, ind in zip(codes, induty):
        j = txt_idx.get(str(c))
        k2 = ind[:KSIC_PREFIX]
        if j is not None and len(k2) == KSIC_PREFIX and k2.strip():
            rows.append(txt_mat[j])
            ind2.append(k2)
    if len(rows) < 2:
        return None, None
    return np.asarray(rows, dtype=np.float32), np.asarray(ind2)


def _pair_stats(M, ind2):
    """상삼각 쌍의 코사인을 같은-KSIC2 / 다른-KSIC2 로 분리. (M 은 L2정규화 → M@M.T = 코사인.)"""
    C = M @ M.T
    n = len(M)
    iu = np.triu_indices(n, k=1)
    cos = C[iu]
    same = (ind2[iu[0]] == ind2[iu[1]])
    return cos[same], cos[~same]     # (같은 산업 쌍, 다른 산업 쌍=널)


def _auc(same, cross):
    """P(같은산업 코사인 > 다른산업 코사인) = Mann-Whitney U 정규화. 표본이 크면 서브샘플."""
    rng = np.random.default_rng(0)
    a = same if len(same) <= 200_000 else rng.choice(same, 200_000, replace=False)
    b = cross if len(cross) <= 200_000 else rng.choice(cross, 200_000, replace=False)
    allv = np.concatenate([a, b])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # 동점 평균순위 보정
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    csum = np.cumsum(cnt)
    avg = (csum - cnt + 1 + csum) / 2.0
    ranks = avg[inv]
    r_a = ranks[:len(a)].sum()
    u_a = r_a - len(a) * (len(a) + 1) / 2.0
    return float(u_a / (len(a) * len(b)))


def derive():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    dev_years = [y for y in cfg["pit_split"]["dev_years"]
                 if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]
    txt_idx, txt_mat = SIM.load_text_vectors()
    if txt_mat is None:
        raise SystemExit("section_vectors.npz 없음 — 텍스트 벡터 캐시를 먼저 빌드하세요.")

    per_year = []
    for y in dev_years:
        M, ind2 = _year_vectors(y, txt_idx, txt_mat)
        if M is None:
            continue
        same, cross = _pair_stats(M, ind2)
        rec = {
            "year": y, "n_firms": int(len(M)),
            "n_same_pairs": int(len(same)), "n_cross_pairs": int(len(cross)),
            "cross_p50": round(float(np.quantile(cross, 0.50)), 4),
            "cross_p90": round(float(np.quantile(cross, 0.90)), 4),
            "cross_p99": round(float(np.quantile(cross, QUANTILE)), 4),
            "same_p50": round(float(np.quantile(same, 0.50)), 4),
            "same_p99": round(float(np.quantile(same, QUANTILE)), 4),
            "auc_same_gt_cross": round(_auc(same, cross), 4),
        }
        per_year.append(rec)
        print(f"  {y}: firms={rec['n_firms']:5d} cross(null) p50={rec['cross_p50']:.3f} "
              f"p90={rec['cross_p90']:.3f} p99={rec['cross_p99']:.3f} | same p50={rec['same_p50']:.3f} "
              f"| AUC={rec['auc_same_gt_cross']:.3f}", file=sys.stderr, flush=True)

    p99s = np.array([r["cross_p99"] for r in per_year], float)
    floor = float(np.round(p99s.mean(), 2))
    result = {
        "axis": "text",
        "method": "cross-industry (KSIC-2 다른) text-cosine null distribution, p{}".format(int(QUANTILE * 100)),
        "ksic_prefix": KSIC_PREFIX, "quantile": QUANTILE,
        "dev_years": [r["year"] for r in per_year],
        "per_year": per_year,
        "per_year_p99": [r["cross_p99"] for r in per_year],
        "mean_p99": round(float(p99s.mean()), 4),
        "std_p99": round(float(p99s.std()), 4),
        "floor_value": floor,
        "mean_auc": round(float(np.mean([r["auc_same_gt_cross"] for r in per_year])), 4),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "derivation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_year"},
                     ensure_ascii=False, indent=2))
    print(f"[floor] text axis absolute floor = {floor} "
          f"(mean null p99 over {len(per_year)} dev years, std={result['std_p99']})",
          file=sys.stderr)
    return result


def derive_for_year(year: int):
    """★ H-2: 그 연도가 서빙에 쓰는 '벡터 공간'에서 널(다른 KSIC2) p99 = 그 공간의 하한.
    프레시(연도별) 벡터라이저는 vocab/IDF 가 dev 공유공간과 달라 절대 코사인 척도가 다르다 →
    같은 METHOD(널 p99)를 그 공간에 적용해 VALUE 를 재유도한다(엔진 _robust_scale 이 스냅샷마다
    IQR 을 재유도하는 것과 동형). section_vectors_{year}.npz 없으면 공유공간(=config 0.52)과 동일.
    산출: data/pit/features/business/section_vectors_{year}.floor.json (하한 결속, no-false-provenance)."""
    from pit import as_of
    npz = ROOT / "data/pit/features/business" / f"section_vectors_{year}.npz"
    if not npz.exists():
        print(f"[floor {year}] 연도별 벡터 없음 → 공유공간 하한(config) 사용", file=sys.stderr)
        return None
    z = np.load(npz, allow_pickle=True)
    key = "keys" if "keys" in z else "corp_codes"
    idx = {str(c): i for i, c in enumerate(z[key])}
    mat = z["matrix"].astype(np.float32)
    feats = as_of(f"{year}-05-15").features
    codes = feats["corp_code"].astype(str).to_numpy()
    induty = feats["induty_code"].fillna("").astype(str).to_numpy()
    rows, ind2 = [], []
    for c, ind in zip(codes, induty):
        j = idx.get(str(c))
        if j is not None and len(ind[:KSIC_PREFIX]) == KSIC_PREFIX and ind[:KSIC_PREFIX].strip():
            rows.append(mat[j]); ind2.append(ind[:KSIC_PREFIX])
    M = np.asarray(rows, dtype=np.float32); ind2 = np.asarray(ind2)
    same, cross = _pair_stats(M, ind2)
    floor = round(float(np.quantile(cross, QUANTILE)), 2)
    out = {
        "axis_floors": {"text": floor},
        "derivation": {
            "space": f"section_vectors_{year}.npz (프레시 FY{year-1} '사업의 내용', 연도별 vocab)",
            "method": f"cross-industry (KSIC-{KSIC_PREFIX} 다른) text-cosine null p{int(QUANTILE*100)}",
            "n_firms": int(len(M)),
            "null_p50": round(float(np.quantile(cross, 0.50)), 4),
            "null_p99": round(float(np.quantile(cross, QUANTILE)), 4),
            "same_p50": round(float(np.quantile(same, 0.50)), 4),
            "auc_same_gt_cross": round(_auc(same, cross), 4),
            "floor_value": floor,
            "note": (f"dev 공유공간 하한 0.52 는 이 프레시 공간(vocab 다름)에 직접 안 맞음 — "
                     f"같은 METHOD 로 이 공간에서 재유도. 순위·점수 불변, 라벨만."),
        },
        "source_script": "scripts/derive_tag_floor.py (derive_for_year)",
    }
    sidecar = npz.with_suffix(".floor.json")
    sidecar.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[floor {year}] space null p99={out['derivation']['null_p99']} → floor={floor} "
          f"(n={len(M)}, AUC={out['derivation']['auc_same_gt_cross']}) → {sidecar.name}", file=sys.stderr)
    return out


def verify_case(year: int, target: str, peer_codes: dict, floor: float):
    """한 스냅샷에서 target 의 원 텍스트 코사인을 peer 들과 비교(하한 적용 전/후 라벨)."""
    txt_idx, txt_mat = SIM.load_text_vectors()
    ti = txt_idx.get(str(target))
    out = {"year": year, "target": target, "floor": floor, "peers": []}
    for label, code in peer_codes.items():
        pj = txt_idx.get(str(code))
        if ti is None or pj is None:
            cos = None
        else:
            cos = float(txt_mat[ti] @ txt_mat[pj])
        out["peers"].append({"name": label, "code": code,
                             "text_cosine": None if cos is None else round(cos, 4),
                             "passes_floor": None if cos is None else bool(cos >= floor)})
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-cj", action="store_true",
                    help="CJ/오뚜기 오판정 케이스를 서브 스냅샷에서 재현")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--year-floor", action="store_true",
                    help="--year 의 연도별 벡터 공간에서 하한 재유도(H-2, 프레시 텍스트)")
    args = ap.parse_args()

    if args.year_floor:
        derive_for_year(args.year)
        sys.exit(0)

    res = derive()

    if args.verify_cj:
        floor = res["floor_value"]
        uni = pd.read_csv(ROOT / "data/pit/universe" / f"universe_{args.year}.csv",
                          dtype=str).fillna("")
        def code_of(name):
            h = uni[uni["corp_name"].str.replace(" ", "") == name.replace(" ", "")]
            return h["corp_code"].iloc[0] if len(h) else None
        cases = {
            "CJ제일제당": {"대한전선(오판정?)": "대한전선", "KG스틸(오판정?)": "KG스틸",
                       "삼성전기(오판정?)": "삼성전기", "두산에너빌리티(오판정?)": "두산에너빌리티",
                       "대상(진짜식품)": "대상", "동원F&B(진짜식품)": "동원F&B",
                       "농심(진짜식품)": "농심", "오뚜기(진짜식품)": "오뚜기"},
        }
        verifications = []
        for tgt_name, peers in cases.items():
            tgt = code_of(tgt_name)
            pc = {k: code_of(v) for k, v in peers.items()}
            v = verify_case(args.year, tgt, {k: c for k, c in pc.items() if c}, floor)
            v["target_name"] = tgt_name
            verifications.append(v)
        (OUT / "verify_cj.json").write_text(
            json.dumps({"floor": floor, "cases": verifications}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("[verify-cj] → runs/web10_tag_floor/verify_cj.json", file=sys.stderr)
