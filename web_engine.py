"""web_engine.py — 웹 표현 계층(읽기 전용 소비자). ★ 엔진/채점기/ORACLE 미수정.

Loop 8 표현 계층(`scripts/build_report.py`)의 **검증된 함수를 그대로 재사용**해,
'한 기업'의 리포트(peer·신뢰등급·확인필요지점)를 on-demand 로 생성한다. 엔진/채점 로직 재구현 0.

정직성·룩어헤드 방어:
  - 스냅샷 = **dev 최신연도(=2022-05-15)**. `pit.as_of(2022-05-15)` 는 2022 파일만 읽으므로
    holdout(2023~2025) 파일에 물리적으로 접근하지 않는다 → 룩어헤드·holdout 개봉 0.
  - 회사명↔corp_code 는 공시 원장(`data/pit/universe/universe_2022.csv`). 시장은 corp_cls.
  - 임계값(응집도 삼분위·편차분위)은 Loop 8 dev 산출 committed `thresholds.json`(동결값) 로드.
  - 화면에 내보내는 필드는 전부 build_report 실제 산출 필드뿐(지어낸 필드 0). WEB_DATA_CONTRACT.md 참조.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_report as BR  # noqa: E402  Loop 8 표현 계층(엔진+채점기 브리지, 이미 검증)

L4_ORDER = BR.L4_ORDER
LOOP8 = ROOT / "runs" / "2026-07-16_loop8"

# corp_cls → 시장 표시명. DART 고정 분류 코드(임의 임계값·튜닝값 아님, 표시 라벨일 뿐).
MARKET_NAMES = {"Y": "유가증권시장(KOSPI)", "K": "코스닥(KOSDAQ)",
                "N": "코넥스(KONEX)", "E": "기타(비상장·외감)"}
# 축(rationale) 표시명 — build_report 축 키 → 한국어 라벨(표시 전용).
AXIS_LABELS = {"industry": "업종", "scale": "규모", "mktcap": "시가총액",
               "text": "사업내용", "growth": "성장성"}


def _load_tag_floors() -> dict:
    """축 라벨 '절대 하한'(WEB-10 ①). ★ 표시 계층 전용 — 순위·유사도 점수·peer 선정 불변.
    값은 데이터 유도(config/tag_thresholds.json, dev 널 분포 p99 = scripts/derive_tag_floor.py).
    특히 text(사업내용)는 사업보고서 상투어 겹침으로 무관 산업이 '유사'로 붙는 오판정을 막는다.
    파일 없거나 파싱 실패면 {} → 하한 미적용(기존 동작으로 안전 폴백)."""
    p = ROOT / "config" / "tag_thresholds.json"
    if p.exists():
        try:
            return dict(json.loads(p.read_text(encoding="utf-8")).get("axis_floors", {}))
        except Exception:
            return {}
    return {}


# dev 공유(shared) 벡터공간의 하한(2022/2024/2025 등 공유 npz 서빙 연도가 사용). 순위/점수와 독립.
TAG_FLOORS = _load_tag_floors()


def _floors_for(year: int) -> dict:
    """서빙 연도의 '벡터 공간'에 맞는 하한. 연도별 프레시 벡터(section_vectors_{year}.npz)가 있으면
    그 공간에서 유도한 사이드카(section_vectors_{year}.floor.json)를, 없으면 공유공간 config(0.52)를.
    ★ 같은 METHOD(널 p99), 공간별 VALUE — 엔진 _robust_scale 이 스냅샷마다 IQR 재유도하는 것과 동형.
    라벨만 좌우, 순위·점수 불변."""
    sc = ROOT / "data" / "pit" / "features" / "business" / f"section_vectors_{year}.floor.json"
    if sc.exists():
        try:
            return dict(json.loads(sc.read_text(encoding="utf-8")).get("axis_floors", {}))
        except Exception:
            return TAG_FLOORS
    return TAG_FLOORS


def _load_text_vectors_for(year: int):
    """스냅샷 연도의 텍스트 벡터. `section_vectors_{year}.npz` 있으면 그것(그 시점 최신 '사업의 내용',
    ★ point-in-time 피처 — mktcap·scale·growth 처럼 스냅샷마다 재산출), 없으면 공유 캐시.
    ★ 엔진 가중치·k·임계값은 불변(apply-only). 벡터라이저(문자 3-gram TF-IDF, L2)는 동일 방법.
    구 스냅샷(2022/2024/2025)은 연도별 파일이 없어 공유 캐시 유지 → 롤백·과거결과 불변."""
    p = ROOT / "data" / "pit" / "features" / "business" / f"section_vectors_{year}.npz"
    if p.exists():
        z = np.load(p, allow_pickle=True)
        key = "keys" if "keys" in z else "corp_codes"
        codes = [str(c) for c in z[key]]
        return {c: i for i, c in enumerate(codes)}, z["matrix"].astype(np.float32)
    return BR.SIM.load_text_vectors()


def _norm(s: str) -> str:
    """회사명 매칭용 정규화(공백 제거·유니코드 정규화·소문자). 표시엔 원문 사용."""
    return unicodedata.normalize("NFKC", str(s or "")).replace(" ", "").strip().lower()


def _snapshot_feature_years() -> list[int]:
    """확정 L6(5축: industry·scale·mktcap·text·growth)에 필요한 피처가 모두 있는 연도 목록.
    ★ 데이터 소스 탐지일 뿐 — 가중치·신뢰등급 임계값은 여전히 dev 동결값(재유도 0).
    segment 는 확정 L6(L4_ORDER)이 미사용하므로 요건에서 제외."""
    # ★ 서빙 스냅샷 연도는 디스크에서 발견(dev/holdout/이후 최신 포함). 서빙은 '데이터 소스'이고
    #   가중치·임계값은 dev 동결(재유도 0) — WEB-5 데이터소스 최신화 원칙. config 연도 상한에 안 묶임.
    sd = ROOT / "data/pit/features/scale"
    years = sorted(int(p.stem.split("_")[1]) for p in sd.glob("scale_*.parquet")
                   if p.stem.split("_")[1].isdigit())
    ok = []
    for y in years:
        need = [ROOT / "data/pit/features" / d / f"{d}_{y}.parquet"
                for d in ("scale", "industry", "mktcap", "growth")]
        need += [ROOT / "data/pit/universe" / f"universe_{y}.csv",
                 ROOT / "data/pit/targets/ratios" / f"ratios_{y}.parquet"]
        if all(p.exists() for p in need):
            ok.append(y)
    return ok


def _snapshot_year() -> int:
    """웹이 조회할 스냅샷 연도(= 데이터 소스). 기본 = 데이터가 완비된 '최신' 연도.
    ★ 이건 데이터 소스 선택일 뿐이다. 확정 엔진 가중치(dev 동결 weights.json)와 신뢰등급 임계값
      (Loop 8 thresholds.json)·τ_r(_ctx 의 dev 유도)은 그대로 로드해 '적용(apply)'만 한다 —
      최신 데이터로 재학습·재유도하지 않는다.
    고정/롤백: env `PEER_SNAPSHOT_YEAR`, 또는 `config/web_snapshot.json` 의 `serve_as_of_year`
      (예: 2022 로 두면 dev 스냅샷으로 롤백). 지정 없으면 완비 최신 연도."""
    import os
    avail = _snapshot_feature_years()
    if not avail:
        raise RuntimeError("스냅샷 피처가 없습니다. PIT 데이터를 먼저 빌드하세요.")
    pin = os.environ.get("PEER_SNAPSHOT_YEAR") or None
    if pin is None:
        cfg_path = ROOT / "config" / "web_snapshot.json"
        if cfg_path.exists():
            try:
                pin = json.loads(cfg_path.read_text(encoding="utf-8")).get("serve_as_of_year")
            except Exception:
                pin = None
    if pin is not None:
        y = int(pin)
        if y not in avail:
            raise RuntimeError(f"요청 스냅샷 연도 {y} 의 피처가 없습니다. 완비 연도: {avail}")
        return y
    return max(avail)


def available_years() -> list[int]:
    """연도 선택 UI 용: 데이터가 완비된 스냅샷 연도(내림차순). ★ 데이터 소스 목록일 뿐 —
    가중치·임계값은 무관하게 dev 동결. 기본(no-year) 스냅샷 로직(_snapshot_year)은 그대로."""
    return sorted(_snapshot_feature_years(), reverse=True)


@lru_cache(maxsize=None)
def _ctx(year: int | None = None) -> dict:
    """스냅샷 컨텍스트(연도별 캐시). year=None 이면 기본 스냅샷 연도(_snapshot_year, Web-5 최신).
    ★ year 는 데이터 소스 선택일 뿐 — 엔진 가중치·신뢰등급 임계값·τ_r 은 여전히 dev 동결값(재유도 0)."""
    cfg = BR.S.load_cfg()
    ratios = cfg["ratios"]
    k = int(cfg["prediction"]["k"])
    min_peers = int(cfg["min_valid_peers"])
    q_sep = float(cfg["separation"]["numerator_over_assets_quantile"])
    cfg_l6, w = BR.l6_cfg_weights(cfg)

    if year is None:
        year = _snapshot_year()
    txt = _load_text_vectors_for(year)          # 연도별 최신 텍스트(있으면) — 데이터소스 계층
    T = f"{year}-05-15"
    dev = [y for y in cfg["pit_split"]["dev_years"]
           if (ROOT / "data/pit/features/scale" / f"scale_{y}.parquet").exists()]

    # 동결 임계값(Loop 8 dev 산출) 로드. 없으면 dev 에서 재계산(폴백).
    thr_path = LOOP8 / "thresholds.json"
    if thr_path.exists():
        thr = json.loads(thr_path.read_text(encoding="utf-8"))["thresholds"]
        thr_source = str(thr_path.relative_to(ROOT))
    else:
        rc = cfg["report"]
        thr = BR.derive_thresholds(dev, cfg_l6, w, k, txt, ratios,
                                   rc["cohesion_quantiles"], rc["deviation_flag_quantile"])
        thr_source = "recomputed(dev)"

    # 예측불가(비교부적합) 임계 τ_r — dev 유도(build_report 와 동일 경로).
    _, tau, _ = BR.LP.separation([f"{y}-05-15" for y in dev], ratios, q_sep)

    # 스냅샷 로드(엔진 허용 피처 + 채점 비율표).
    tables, _ = BR.S.ratio_tables([year], ratios)
    rt = tables[T]
    tg_raw = BR.as_of(T, with_targets=True).targets.set_index("corp_code")
    ft = BR.as_of(T).features
    assets = ft.set_index("corp_code")["총자산"] if "총자산" in ft.columns else pd.Series(dtype=float)
    _, A = BR.year_engine(year, cfg_l6, txt)
    codes = [str(c) for c in A["codes"]]
    idx = {c: i for i, c in enumerate(codes)}
    induty = [str(x) for x in A["induty"]]

    # 회사명 원장(universe): corp_code ↔ corp_name/corp_cls/stock_code.
    uni = pd.read_csv(ROOT / "data/pit/universe" / f"universe_{year}.csv", dtype=str).fillna("")
    name_of, cls_of, stock_of = {}, {}, {}
    name_index: dict[str, list[str]] = {}
    for _, row in uni.iterrows():
        c = str(row["corp_code"]).strip()
        name_of[c] = row.get("corp_name", "").strip()
        cls_of[c] = row.get("corp_cls", "").strip()
        stock_of[c] = row.get("stock_code", "").strip()
        name_index.setdefault(_norm(row.get("corp_name", "")), []).append(c)

    return {
        "year": year, "T": T, "k": k, "min_peers": min_peers, "ratios": ratios,
        "w": w, "thr": thr, "thr_source": thr_source, "tau": tau,
        "A": A, "codes": codes, "idx": idx, "induty": induty,
        "rt": rt, "tg_raw": tg_raw, "assets": assets,
        "name_of": name_of, "cls_of": cls_of, "stock_of": stock_of, "name_index": name_index,
    }


def warmup() -> dict:
    """스냅샷 컨텍스트를 미리 구축(첫 질의 지연 방지). 메타 요약 반환."""
    c = _ctx()
    return {"as_of": c["T"], "n_universe": len(c["codes"]),
            "thresholds": c["thr"], "thresholds_source": c["thr_source"]}


def suggest(name: str, limit: int = 8, year: int | None = None) -> list[dict]:
    """부분일치 후보(오타·상호 확인용). 랭킹 가능(스냅샷 피처 존재)한 후보 우선."""
    c = _ctx(year)
    q = _norm(name)
    if not q:
        return []
    hits = []
    for code, disp in c["name_of"].items():
        n = _norm(disp)
        if q in n or n in q:
            hits.append((code, disp, n == q, code in c["idx"]))
    # 정확일치 > 랭킹가능 > 이름길이(근접) 순.
    hits.sort(key=lambda t: (not t[2], not t[3], len(t[1])))
    seen, out = set(), []
    for code, disp, _exact, rankable in hits:
        if disp in seen:
            continue
        seen.add(disp)
        out.append({"corp_code": code, "corp_name": disp, "rankable": rankable})
        if len(out) >= limit:
            break
    return out


def _target_meta(c: dict, code: str, i: int) -> dict:
    """타겟 메타(실제 데이터만): 회사명·시장·업종코드·평가시점·회계연도·종목코드."""
    return {
        "corp_code": code,
        "corp_name": c["name_of"].get(code, code),
        "market": MARKET_NAMES.get(c["cls_of"].get(code, ""), c["cls_of"].get(code, "") or "미상"),
        "induty_code": c["induty"][i] if c["induty"][i] not in ("", "nan") else None,
        "stock_code": c["stock_of"].get(code) or None,
        "as_of": c["T"],
        "fiscal_year": c["year"] - 1,  # 5/15 스냅샷 = 직전 사업연도 사업보고서(reader.py 스냅샷 의미)
    }


def query(name: str, year: int | None = None) -> dict:
    """회사명 → 엔진 L6 랭킹 → 리포트. build_report 함수 그대로 사용(재구현 0).
    year=None 이면 기본 스냅샷(최신), 지정 시 그 연도 스냅샷에 확정 엔진을 적용(재학습 0).

    반환 dict:
      ok=False + reason(not_found | not_rankable | ambiguous) + suggestions
      ok=True  + target(메타) + peer_confidence + peer_cohesion + peers[] + ratios[]
                 (필드는 전부 build_report 실제 산출 — WEB_DATA_CONTRACT.md)
    """
    c = _ctx(year)
    q = _norm(name)
    if not q:
        return {"ok": False, "reason": "empty", "message": "회사명을 입력하세요."}

    codes = c["name_index"].get(q, [])
    if not codes:
        sug = suggest(name, year=year)
        return {"ok": False, "reason": "not_found",
                "message": "해당 회사를 찾을 수 없습니다. 상호(정식 등록명)를 확인하세요.",
                "suggestions": sug}

    # 정확일치 다수 → 랭킹 가능한 것 우선. 여전히 다수면 후보 제시.
    rankable = [x for x in codes if x in c["idx"]]
    if not rankable:
        return {"ok": False, "reason": "not_rankable",
                "message": (f"해당 회사는 공시 원장에는 있으나 {c['T']} 시점 비교용 재무·산업 피처가 "
                            "없어 순위를 낼 수 없습니다(비상장·자료 미제출 등)."),
                "suggestions": suggest(name, year=year)}
    if len({c["name_of"][x] for x in rankable}) > 1 or len(rankable) > 1:
        # 동명이인(코드 다름) — 후보를 제시하되, 그중 하나로 진행하지 않는다(억지 결과 0).
        if len(rankable) > 1:
            return {"ok": False, "reason": "ambiguous",
                    "message": "같은 이름의 대상이 여러 건입니다. 후보 중 선택하세요.",
                    "suggestions": [{"corp_code": x, "corp_name": c["name_of"][x],
                                     "rankable": True} for x in rankable]}

    code = rankable[0]
    i = c["idx"][code]

    # ★ Loop 8 검증 함수 그대로 — 신뢰등급·근거·확인필요지점을 재계산하지 않는다.
    coh, peers, order = BR.target_report(
        c["A"], c["w"], i, c["k"], L4_ORDER, c["rt"], c["tg_raw"], c["assets"],
        c["tau"], c["min_peers"])
    pg = BR.grade(coh, c["thr"])
    ratio_block = BR.build_ratio_block(
        order, c["A"]["codes"], i, c["rt"], c["tg_raw"], c["assets"], c["ratios"],
        c["tau"], c["min_peers"], c["thr"]["dev_flag"], pg)

    # peer 코드 → 회사명(원장). 축 근거는 실제 rationale 그대로 + 표시 라벨만 부여.
    # ★ WEB-10 ①: 축 라벨에 '절대 하한'(TAG_FLOORS) 적용 — 표시 계층만. 상투어 겹침으로
    #   무관 산업이 '사업내용 유사'로 붙는 오판정 차단. 순위·유사도 점수·peer 선정은 전부 불변.
    #   하한 비교는 '원(raw) 축 유사도'(가중 전 sim)에 한다 — rationale 은 w·sim 이므로 부적합.
    raw_axis = {ax: BR.SIM.SIMS[ax](c["A"], i) for ax in L4_ORDER}
    floors = _floors_for(c["year"])             # ★ 서빙 연도의 벡터공간에 맞는 하한(공유=0.52, 프레시=유도)
    for p in peers:
        p["peer_name"] = c["name_of"].get(p["peer_code"], p["peer_code"])
        j = c["idx"].get(p["peer_code"])
        # 표시용: 실제 rationale 기여 상위 2축(양수만)에 한국어 라벨. 값·판정 미변경(정렬·라벨뿐).
        top = sorted(p["rationale"].items(), key=lambda kv: kv[1], reverse=True)
        labels = []
        for axkey, v in top[:2]:
            if v <= 0:
                continue
            fl = floors.get(axkey)
            # 원 유사도가 하한 미만이면 라벨 제거(상투어만으로 붙은 '유사' 주장 차단).
            if fl is not None and j is not None and float(raw_axis[axkey][j]) < float(fl):
                continue
            labels.append(AXIS_LABELS.get(axkey, axkey))
        p["top_axes"] = labels

    return {
        "ok": True,
        "target": _target_meta(c, code, i),
        "peer_confidence": pg,
        "peer_cohesion": round(float(coh), 4),
        "n_peers": len(peers),
        "peers": peers,
        "ratios": ratio_block,
        "axis_labels": AXIS_LABELS,
        "engine": "similarity_l6",
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="web_engine 단일 기업 질의(디버그)")
    ap.add_argument("name", help="회사명(정식 등록명)")
    args = ap.parse_args()
    print(json.dumps(query(args.name), ensure_ascii=False, indent=2))
