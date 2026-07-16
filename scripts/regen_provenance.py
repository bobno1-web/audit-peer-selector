#!/usr/bin/env python3
"""교정 targets 출처 매니페스트 (Loop 6-B PART 1) — 커밋되는 검증 가능 기록.

data/pit/targets 는 gitignore 라 커밋 저장소만으로는 '교정 여부'를 확인할 수 없다. 이 스크립트는
원본(runs/…/original) 대비 라이브(교정본)의 **실제 변경**을 계정별 올바른 소스로 재집계하고,
두 상태의 **콘텐츠 지문(원본/교정)** 을 provenance.json 에 남긴다(커밋). 검증방은 재생성 후 지문을
비교해 교정을 독립 확인한다.

★ 이전 regen_summary.json 의 '총자산 11775' 는 diff 카운터 버그(총자산 old 값을 ratios 파케이에서 읽어
  항상 None 과 비교)였다 — 총자산은 별칭 1개라 실제 변경 0. 이 매니페스트가 정정한다.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provenance as PV                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIT = ROOT / "data" / "pit"
TP = PIT / "targets" / "ratios"
SP = PIT / "features" / "scale"
RUN = ROOT / "runs" / "2026-07-16_regen_targets"
ORIG = RUN / "original"
DEV_YEARS = list(range(2016, 2023))
TARGET_ACC = PV.TARGET_ACCOUNTS                             # 6 채점계정(ratios)
SCALE_ACC = ["매출액", "총자산"]                             # scale 소스 계정


def acct_changes():
    """계정별 실제 변경 firm-year 수(원본 대비 라이브). 올바른 소스 파케이 사용."""
    counts = {}
    changed_firms = set()
    for y in DEV_YEARS:
        ol = pd.read_parquet(ORIG / f"ratios_{y}.parquet").set_index("corp_code")
        lv = pd.read_parquet(TP / f"ratios_{y}.parquet").set_index("corp_code")
        for a in TARGET_ACC:
            if a not in ol.columns:
                continue
            o = ol[a]; n = lv[a].reindex(o.index)
            d = (o.fillna(-1) != n.fillna(-1))
            counts[a] = counts.get(a, 0) + int(d.sum())
            for cc in o.index[d]:
                changed_firms.add((y, cc))
        # 스케일 소스(총자산) — 올바른 파케이에서 비교
        os_ = pd.read_parquet(ORIG / f"scale_{y}.parquet").set_index("corp_code")
        ls_ = pd.read_parquet(SP / f"scale_{y}.parquet").set_index("corp_code")
        for a in ["총자산"]:
            if a in os_.columns:
                o = os_[a]; n = ls_[a].reindex(o.index)
                counts[a] = counts.get(a, 0) + int((o.fillna(-1) != n.fillna(-1)).sum())
    return counts, len(changed_firms)


def main():
    if not ORIG.exists():
        raise SystemExit("original/ 백업 없음 — regen_swap 미실행? provenance 생성 불가.")
    counts, n_firms = acct_changes()
    orig_digest = PV.combined_targets_digest(DEV_YEARS, ratios_dir=ORIG)
    corr_digest = PV.combined_targets_digest(DEV_YEARS, ratios_dir=TP)
    manifest = {
        "purpose": "교정 targets 출처(라벨↔실제 데이터 결속) — data/pit gitignore 보완",
        "dev_years": DEV_YEARS,
        "resolver_fix": "pit_build.extract 별칭 우선순위(순수 매출채권 > 합산) — D-026",
        "changes_by_account": counts,                       # ★ 정정: 매출채권 767, 매출원가 25, 총자산 0
        "n_firm_years_changed": n_firms,
        "original_targets_digest": orig_digest,             # 교정 전 지문
        "corrected_targets_digest": corr_digest,            # 교정 후 지문(= 라이브가 이것과 일치해야 함)
        "digest_differs": orig_digest != corr_digest,       # True 여야 교정 실제 반영
        "per_year_corrected_digest": PV.targets_digest(DEV_YEARS, ratios_dir=TP),
        "amendment_kept_old_note": "T후 정정공시(amendment) 반환 firm-year 는 옛값 유지(룩어헤드 차단). "
                                   "DATA_CARD 기록. 원본 filing 이 API 로 재취득 불가라 교정 미적용(안전).",
        "hash_method": "sha256(sorted corp_code + 6 채점계정 콘텐츠; parquet write 독립)",
    }
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({"changes_by_account": counts, "n_firm_years_changed": n_firms,
                      "digest_differs": manifest["digest_differs"],
                      "corrected_digest": corr_digest[:16] + "…"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
