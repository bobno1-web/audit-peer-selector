#!/usr/bin/env python3
"""출처(provenance) 지문 — 산출물 라벨을 '실제 데이터 상태'에 묶는 공용 해시 (Loop 6-B).

문제(검증방 발견): 결과 파일이 "targets: corrected" / "median@k10" 라벨을 달지만, 실제 target 데이터·
peer 수와 **묶여 있지 않다**. 게다가 data/pit/targets 는 gitignore 라 커밋 저장소만으로는 라벨을 **독립
검증할 수 없다**. → 라벨과 실제가 어긋나도(예: 미교정 데이터에 'corrected' 라벨) 아무도 못 잡는다.

이 모듈은 **write-독립(파케이 바이트가 아니라 콘텐츠) content-hash** 를 제공한다:
  - target_content_hash(year): 그 해 targets 의 (corp_code, 6개 채점계정) 정렬 콘텐츠 SHA-256.
    파케이 압축·메타·pandas 버전과 무관 → 재생성해도 같은 데이터면 같은 해시(독립 재현 가능).
  - combined_targets_digest(years): dev 전체 지문.
  - peers_k(path): peers.parquet 의 실제 peer 수(라벨 k 와 대조용).
결과 생성기(finalize/showdown)는 이 지문을 결과 JSON 에 **스탬프**하고, test_provenance_integrity 가
라이브 데이터에서 재계산해 **일치 여부를 강제**한다(불일치 = 거짓 라벨 = FAIL).
"""
import hashlib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TP = ROOT / "data" / "pit" / "targets" / "ratios"
TARGET_ACCOUNTS = ["매출액", "매출원가", "매출총이익", "영업이익", "재고자산", "매출채권"]


def target_content_hash(year, ratios_dir=TP):
    """그 해 targets 의 콘텐츠 지문(파케이 바이트 아님 → write 독립). 파일 없으면 ''."""
    p = Path(ratios_dir) / f"ratios_{year}.parquet"
    if not p.exists():
        return ""
    df = pd.read_parquet(p)
    cols = ["corp_code"] + [a for a in TARGET_ACCOUNTS if a in df.columns]
    df = df[cols].sort_values("corp_code")
    lines = []
    for _, r in df.iterrows():
        vals = "|".join("" if pd.isna(r[a]) else str(int(r[a]))
                        for a in TARGET_ACCOUNTS if a in df.columns)
        lines.append(f"{r['corp_code']}:{vals}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def targets_digest(years, ratios_dir=TP):
    return {int(y): target_content_hash(y, ratios_dir) for y in years}


def combined_targets_digest(years, ratios_dir=TP):
    """dev 전체 targets 지문(연도별 해시를 정렬 결합)."""
    h = hashlib.sha256()
    for y in sorted(int(y) for y in years):
        h.update(target_content_hash(y, ratios_dir).encode("utf-8"))
    return h.hexdigest()


def peers_k(path):
    """peers.parquet 의 실제 peer 수(타겟당 최대 rank). 라벨 k 와 대조용."""
    df = pd.read_parquet(path)
    if not len(df) or "rank" not in df.columns:
        return 0
    return int(df["rank"].max())


def stamp(years, ratios_dir=TP):
    """결과 JSON 에 넣을 출처 스탬프."""
    return {"targets_combined_digest": combined_targets_digest(years, ratios_dir),
            "targets_per_year_digest": targets_digest(years, ratios_dir),
            "hash_method": "sha256(sorted corp_code + 6 채점계정 콘텐츠; write-독립)"}


# ── 검증 헬퍼(test_provenance_integrity 가 사용; 거짓 라벨 탐지의 핵심) ──
def stamped_digest(result_dict):
    """결과 dict 에 스탬프된 target 지문(없으면 None)."""
    return (result_dict.get("provenance") or {}).get("targets_combined_digest")


def label_matches_live(result_dict, years, ratios_dir=TP):
    """★ 결과의 스탬프 지문이 '현재 라이브 target 데이터'와 일치하는가.
    불일치 = 라벨(예: 'corrected')이 실제 데이터와 어긋남 = 거짓 라벨(FAIL 대상)."""
    sd = stamped_digest(result_dict)
    return sd is not None and sd == combined_targets_digest(years, ratios_dir)


def k_label_matches_peers(k_label, peers_path):
    """★ 라벨 k 가 peers.parquet 의 실제 peer 수와 일치하는가(stale k 탐지)."""
    return int(k_label) == peers_k(peers_path)
