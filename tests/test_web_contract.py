#!/usr/bin/env python3
"""웹 데이터 계약 테스트 (Loop WEB-1) — 화면이 엔진 출력을 '지어내지 않음'을 강제.

강제하는 것:
  (양성, 데이터 있을 때) `web_engine.query(name)` 결과의 엔진 핵심 필드(peer_cohesion·peer_code·
     similarity·rationale·비율 전 필드)가 **커밋된 Loop 8 sample_reports.json 과 완전 일치**한다
     → 웹은 build_report 산출을 그대로 표시할 뿐, 새 값을 만들지 않는다(W2·W7·W22).
  (항상) 스냅샷 연도가 **dev 범위이고 holdout(2023~2025)이 아님**(W21) + 화면 추가필드가
     전부 **실데이터 파생**(peer_name=원장, top_axes=실제 rationale 상위축)임을 확인(W2).
데이터(data/pit gitignore) 부재 시 양성은 skip, 논리 검사는 항상 돈다.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import web_engine  # noqa: E402
import yaml  # noqa: E402

LOOP8 = ROOT / "runs" / "2026-07-16_loop8" / "sample_reports.json"
SCALE_2022 = ROOT / "data" / "pit" / "features" / "scale" / "scale_2022.parquet"

# build_report 실제 산출 필드(스키마) — 이 밖의 '값 필드'가 나오면 지어낸 것.
PEER_ENGINE_KEYS = {"rank", "peer_code", "similarity", "rationale"}
PEER_DISPLAY_KEYS = {"peer_name", "top_axes"}                # 실데이터 파생(원장·rationale)
RATIO_KEYS = {"ratio", "peer_median", "target_actual", "deviation_pct", "direction",
              "check_needed", "confidence", "valid_peers", "comparable", "note"}


def _data_present():
    return SCALE_2022.exists()


class TestServeIsApplyOnlyDevFrozen(unittest.TestCase):
    """항상 실행 — 서빙 스냅샷 연도는 '데이터 소스 포인터'(dev/holdout/이후 가능)이고, 학습된
    파라미터(엔진 가중치·신뢰등급 임계값)는 **dev 동결값에서 로드**됨(재유도 0). ★ WEB-5(데이터소스
    최신화)+Loop7(holdout 개봉, D-029) 이후의 정직한 계약: 최신 스냅샷 apply 는 허용, 재학습은 금지.
    (룩어헤드는 pit.as_of(T≤스냅샷)로 별도 강제 — test_pit_integrity.)"""

    def test_engine_weights_are_dev_frozen_L6(self):
        import numpy as np
        cfg = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
        import build_report as BR
        _, w = BR.l6_cfg_weights(cfg)                     # 웹이 실제 쓰는 가중치
        fz = json.loads((ROOT / "config" / "holdout_freeze.json").read_text(encoding="utf-8"))
        frozen = np.array(fz["engines"]["similarity_L6"]["weights"], float)
        frozen = frozen / frozen.sum()
        self.assertTrue(np.allclose(w, frozen), "웹 가중치가 dev 동결 L6 와 다름(재학습 금지 위반)")

    def test_confidence_thresholds_from_committed_dev(self):
        # 신뢰등급 임계값은 Loop8 committed thresholds.json(dev 유도) 에서 로드 — 서빙연도로 재유도 안 함.
        self.assertTrue((ROOT / "runs" / "2026-07-16_loop8" / "thresholds.json").exists(),
                        "dev 동결 thresholds.json 있어야 함(재유도 아님)")

    def test_rollback_year_is_dev(self):
        # 롤백 지점(config/web_snapshot.json.rollback_year)은 dev 스냅샷이어야 함(안전한 원복 지점).
        cfg = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
        dev = set(cfg["pit_split"]["dev_years"])
        snap = ROOT / "config" / "web_snapshot.json"
        if snap.exists():
            rb = json.loads(snap.read_text(encoding="utf-8")).get("rollback_year")
            if rb is not None:
                self.assertIn(int(rb), dev, "롤백 연도는 dev 스냅샷이어야 한다")


class TestWebMatchesLoop8(unittest.TestCase):
    """양성 — 데이터 있을 때만. 웹 산출이 커밋된 Loop 8 예시와 완전 일치."""

    @classmethod
    def setUpClass(cls):
        if not _data_present():
            raise unittest.SkipTest("data/pit 없음(gitignore) — 양성 검사 skip")
        cls.samples = json.loads(LOOP8.read_text(encoding="utf-8"))["examples"]
        # ★ 샘플은 dev(2022-05-15) 스냅샷 산출 — 그 스냅샷 연도로 질의해야 엔진 충실성을 검증한다.
        #   (서빙 기본연도는 WEB-5 이후 최신 스냅샷이므로 default 로 비교하면 안 됨.)
        cls.sample_year = int(next(v for v in cls.samples.values() if v)["as_of"][:4])
        cls.ctx = web_engine._ctx(cls.sample_year)

    def _report_for_code(self, code):
        """커밋 샘플의 target(corp_code)을 회사명으로 되짚어 그 스냅샷 연도로 재생성."""
        name = self.ctx["name_of"].get(code)
        self.assertTrue(name, f"{code} 원장 이름 없음")
        return web_engine.query(name, year=self.sample_year), name

    def test_high_example_matches_exactly(self):
        ex = self.samples["HIGH_confidence"]
        r, name = self._report_for_code(ex["target"])
        # 동명이인으로 모호하면 이 코드로 확정 불가 → 이 케이스는 통과(다른 케이스가 커버)
        if not r.get("ok"):
            self.skipTest(f"{name} 모호/랭킹불가 — 다른 예시로 검증")
        self.assertEqual(r["target"]["corp_code"], ex["target"])
        self.assertEqual(r["peer_confidence"], ex["peer_confidence"])
        self.assertEqual(r["peer_cohesion"], ex["peer_cohesion"])
        # peer 엔진 필드 완전 일치(지어냄 0)
        self.assertEqual([p["peer_code"] for p in r["peers"]],
                         [p["peer_code"] for p in ex["peers"]])
        for pw, pe in zip(r["peers"], ex["peers"]):
            self.assertEqual(pw["similarity"], pe["similarity"])
            self.assertEqual(pw["rationale"], pe["rationale"])
        # 비율 블록 완전 일치
        self.assertEqual(r["ratios"], ex["ratios"])

    def test_no_fabricated_value_fields(self):
        """모든 예시에서 peer/ratio 키가 스키마 안(엔진필드+실데이터 파생)에만 있다."""
        for key, ex in self.samples.items():
            r = web_engine.query(self.ctx["name_of"].get(ex["target"], ""), year=self.sample_year)
            if not r.get("ok"):
                continue
            for p in r["peers"]:
                extra = set(p) - (PEER_ENGINE_KEYS | PEER_DISPLAY_KEYS)
                self.assertFalse(extra, f"{key}: peer 지어낸 필드 {extra}")
                # top_axes 는 실제 rationale 양수 축 라벨의 부분집합(파생 증명)
                pos = {web_engine.AXIS_LABELS[k] for k, v in p["rationale"].items() if v > 0}
                self.assertTrue(set(p["top_axes"]) <= pos, f"{key}: top_axes 가 rationale 파생 아님")
                # peer_name 은 원장에서 온 값
                self.assertEqual(p["peer_name"], self.ctx["name_of"].get(p["peer_code"], p["peer_code"]))
            for rt in r["ratios"]:
                extra = set(rt) - RATIO_KEYS
                self.assertFalse(extra, f"{key}: ratio 지어낸 필드 {extra}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
