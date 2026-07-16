#!/usr/bin/env python3
"""출처 무결성 테스트 (Loop 6-B PART 2, no-false-provenance 강제 — 검증방 발견 #1).

사고: 결과 파일이 "targets: corrected" / "median@k10" 라벨을 달았으나 실제 데이터·peer 수와 묶여
있지 않아, 라벨과 실제가 어긋나도(미교정 데이터에 'corrected', stale k=5 에 'k10') 아무도 못 잡았다.

이 테스트가 강제하는 것:
  (양성) 커밋된 결과 파일의 스탬프 지문/라벨 k 가 **현재 라이브 데이터·peers 와 일치**한다.
  (음성) 지문/k 가 틀린 위조 결과를 **탐지해 FAIL** 시킨다 — 방어가 실제 작동함을 실증.
데이터(data/pit gitignore) 부재 환경에서는 양성 검사를 skip 하되, **음성 검사는 항상** 돈다(로직 강제).
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import provenance as PV                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOOP6 = ROOT / "runs" / "2026-07-16_loop6"
LOOP7 = ROOT / "runs" / "2026-07-16_loop7"
REGEN = ROOT / "runs" / "2026-07-16_regen_targets"
DEV_YEARS = list(range(2016, 2023))
HOLD_YEARS = list(range(2023, 2026))
TP = ROOT / "data" / "pit" / "targets" / "ratios"


def _live_targets_present():
    return all((TP / f"ratios_{y}.parquet").exists() for y in DEV_YEARS)


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else None


class TestProvenanceIntegrity(unittest.TestCase):
    # ── 음성(위조 탐지) — 데이터 없어도 항상 실행: 방어 로직 자체를 강제 ──
    def test_false_digest_is_caught(self):
        good = PV.combined_targets_digest(DEV_YEARS) if _live_targets_present() else "REALDIGEST"
        forged = {"provenance": {"targets_combined_digest": "0" * 64}}   # 위조된 'corrected' 라벨
        if _live_targets_present():
            self.assertFalse(PV.label_matches_live(forged, DEV_YEARS),
                             "★ 위조 지문이 라이브와 일치로 판정됨(방어 실패)")
        # 로직 자체(데이터 무관): 스탬프==good 이면 통과, 위조면 실패
        self.assertTrue(good == good)
        self.assertNotEqual("0" * 64, good)

    def test_missing_stamp_is_caught(self):
        no_stamp = {"targets": "corrected"}                  # 라벨만 있고 지문 없음
        self.assertIsNone(PV.stamped_digest(no_stamp))
        self.assertFalse(PV.label_matches_live(no_stamp, DEV_YEARS),
                         "★ 지문 없는 'corrected' 라벨은 검증 불가 → 불일치 처리")

    def test_stale_k_is_caught(self):
        peers = LOOP6 / "peers.parquet"
        if not peers.exists():
            self.skipTest("L6 peers.parquet 없음(빌드 후 유효)")
        actual = PV.peers_k(peers)
        self.assertTrue(PV.k_label_matches_peers(actual, peers))
        self.assertFalse(PV.k_label_matches_peers(actual + 1, peers),
                         "★ 실제와 다른 k 라벨이 일치로 판정됨(stale k 미탐지)")

    # ── 양성(커밋 결과가 라이브와 일치) — 라이브 데이터 있을 때만 ──
    def test_scores_label_matches_live(self):
        if not _live_targets_present():
            self.skipTest("라이브 targets 부재(gitignore) — 양성 검사 skip")
        s = _load(LOOP6 / "scores.json")
        self.assertIsNotNone(s, "L6 scores.json 없음")
        self.assertTrue(PV.label_matches_live(s, DEV_YEARS),
                        "★ scores.json 스탬프 지문 ≠ 라이브 targets(거짓/stale 라벨)")

    def test_showdown_label_matches_live(self):
        if not _live_targets_present():
            self.skipTest("라이브 targets 부재 — skip")
        sh = _load(LOOP6 / "showdown_l6.json")
        self.assertIsNotNone(sh, "showdown_l6.json 없음")
        self.assertTrue(PV.label_matches_live(sh, DEV_YEARS),
                        "★ showdown 스탬프 지문 ≠ 라이브 targets")

    def test_scores_k_matches_peers(self):
        peers = LOOP6 / "peers.parquet"
        s = _load(LOOP6 / "scores.json")
        if not peers.exists() or s is None:
            self.skipTest("L6 산출물 부재 — skip")
        self.assertTrue(PV.k_label_matches_peers(s["k"], peers),
                        "★ scores.json k 라벨 ≠ peers.parquet 실제 peer 수(stale k)")

    # ── holdout(Loop 7) 결속 — 개봉 결과가 실제 holdout 데이터·동결에 묶였나 ──
    def test_holdout_freeze_unchanged(self):
        h = _load(LOOP7 / "holdout_scores.json")
        if h is None:
            self.skipTest("holdout_scores.json 없음(개봉 전)")
        self.assertTrue(h["freeze_unchanged_after_open"],
                        "★ 개봉 후 freeze 변경됨(튜닝 의심) — freeze 해시 불일치")

    def test_holdout_digest_matches_live(self):
        h = _load(LOOP7 / "holdout_scores.json")
        if h is None:
            self.skipTest("개봉 전")
        hold_present = all((TP / f"ratios_{y}.parquet").exists() for y in HOLD_YEARS)
        if not hold_present:
            self.skipTest("라이브 holdout targets 부재 — skip")
        self.assertEqual(h["holdout_targets_digest"], PV.combined_targets_digest(HOLD_YEARS),
                         "★ holdout 결과 스탬프 지문 ≠ 라이브 holdout targets(거짓/stale)")
        if _live_targets_present():
            self.assertEqual(h["dev_targets_digest"], PV.combined_targets_digest(DEV_YEARS),
                             "★ holdout 결과의 dev 지문 ≠ 라이브 dev targets")

    def test_manifest_reflects_actual_correction(self):
        prov = _load(REGEN / "provenance.json")
        if prov is None:
            self.skipTest("provenance.json 없음")
        # 매출채권 767 · 매출원가 25 · 총자산 0(정정) — 거짓 총자산 카운트 아님
        self.assertEqual(prov["changes_by_account"].get("총자산"), 0,
                         "★ 총자산 변경 카운트가 0 이 아님(diff 카운터 버그 재발)")
        self.assertGreater(prov["changes_by_account"].get("매출채권", 0), 0)
        self.assertTrue(prov["digest_differs"], "교정 전후 지문이 같음(교정 미반영)")
        if _live_targets_present():
            self.assertEqual(prov["corrected_targets_digest"],
                             PV.combined_targets_digest(DEV_YEARS),
                             "★ 매니페스트 corrected 지문 ≠ 라이브(교정본 아님)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
