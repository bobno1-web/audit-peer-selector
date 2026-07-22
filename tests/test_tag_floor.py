#!/usr/bin/env python3
"""태그 절대하한 테스트 (WEB-10 ①) — 하한이 '라벨만' 바꾸고 순위·점수는 불변임을 강제.

강제하는 것:
  1) (항상) 하한 값은 config/tag_thresholds.json 에서 온다(하드코딩 아님). text 축에 하한 존재.
  2) (데이터 있을 때) 하한 적용 결과 top_axes 는 '하한 미적용 top_axes'의 부분집합이다
     (라벨은 제거만, 추가 없음) — 표시 계층만.
  3) (데이터 있을 때) 하한 on/off 로 peer_code·similarity·rationale·순서가 완전 동일하다
     (순위·유사도 점수 불변, T5/T19).
  4) (데이터 있을 때) 원 텍스트 코사인 < floor 인 peer 는 '사업내용' 라벨을 갖지 않는다(오판정 차단).
데이터(data/pit gitignore) 부재 시 2~4 는 skip, 1 은 항상 돈다.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "engines" / "similarity"))

import web_engine as W  # noqa: E402

SCALE_2022 = ROOT / "data" / "pit" / "features" / "scale" / "scale_2022.parquet"
CFG = ROOT / "config" / "tag_thresholds.json"


def _data_present():
    return SCALE_2022.exists()


class TestFloorFromConfig(unittest.TestCase):
    """항상 실행 — 하한 값은 데이터 유도 config 에서(임의 리터럴 아님)."""

    def test_floor_loaded_from_config(self):
        self.assertTrue(CFG.exists(), "config/tag_thresholds.json 있어야 함")
        floors = json.loads(CFG.read_text(encoding="utf-8"))["axis_floors"]
        self.assertIn("text", floors, "text 축 하한 필요(상투어 널)")
        self.assertEqual(W.TAG_FLOORS.get("text"), floors["text"],
                         "web_engine 이 config 하한을 그대로 로드해야 함")
        # 하한은 [0,1] 코사인 척도 안(정의역 정합)
        self.assertTrue(0.0 < float(floors["text"]) < 1.0)


class TestFloorLabelsOnly(unittest.TestCase):
    """데이터 있을 때 — 하한은 라벨만 바꾸고 순위·점수는 불변."""

    @classmethod
    def setUpClass(cls):
        if not _data_present():
            raise unittest.SkipTest("data/pit 없음(gitignore) — skip")
        # 랭킹 가능한 임의 타겟 몇 개(원장 최상단에서 rankable 탐색; 종목명 리터럴 없음)
        ctx = W._ctx()
        cls.year = ctx["year"]
        cls.names = []
        for code in ctx["idx"]:                     # rankable(피처 존재) corp
            nm = ctx["name_of"].get(code)
            if nm:
                cls.names.append(nm)
            if len(cls.names) >= 5:
                break

    def _query_with_floors(self, name, floors):
        saved = W._floors_for
        try:
            W._floors_for = lambda y: floors        # 연도별 사이드카/공유 무관하게 강제
            return W.query(name, year=self.year)
        finally:
            W._floors_for = saved

    def test_ranking_and_scores_invariant(self):
        """하한 on/off — peer_code·similarity·rationale·순서 완전 동일."""
        for name in self.names:
            on = self._query_with_floors(name, {"text": 0.52})
            off = self._query_with_floors(name, {})
            if not (on.get("ok") and off.get("ok")):
                continue
            self.assertEqual([p["peer_code"] for p in on["peers"]],
                             [p["peer_code"] for p in off["peers"]], f"{name}: 순위 바뀜")
            for a, b in zip(on["peers"], off["peers"]):
                self.assertEqual(a["similarity"], b["similarity"], f"{name}: 유사도 바뀜")
                self.assertEqual(a["rationale"], b["rationale"], f"{name}: rationale 바뀜")
            self.assertEqual(on["peer_cohesion"], off["peer_cohesion"], f"{name}: 응집도 바뀜")

    def test_labels_only_removed_never_added(self):
        """하한 적용 top_axes ⊆ 미적용 top_axes (라벨은 제거만)."""
        for name in self.names:
            on = self._query_with_floors(name, {"text": 0.52})
            off = self._query_with_floors(name, {})
            if not (on.get("ok") and off.get("ok")):
                continue
            for a, b in zip(on["peers"], off["peers"]):
                self.assertTrue(set(a["top_axes"]) <= set(b["top_axes"]),
                                f"{name}: 하한이 라벨을 추가함 {a['top_axes']} ⊄ {b['top_axes']}")

    def test_below_floor_has_no_text_label(self):
        """원 텍스트 코사인 < floor 인 peer 는 '사업내용' 라벨 없음(오판정 차단)."""
        import run as SIM
        txt_label = W.AXIS_LABELS["text"]
        floor = float(W._floors_for(self.year)["text"])     # 그 연도 벡터공간의 하한
        ctx = W._ctx(self.year)
        for name in self.names:
            r = W.query(name, year=self.year)
            if not r.get("ok"):
                continue
            i = ctx["idx"][r["target"]["corp_code"]]
            raw_text = SIM.SIMS["text"](ctx["A"], i)
            for p in r["peers"]:
                j = ctx["idx"].get(p["peer_code"])
                if j is None:
                    continue
                if float(raw_text[j]) < floor:
                    self.assertNotIn(txt_label, p["top_axes"],
                                     f"{name}→{p['peer_name']}: cos<{floor}인데 '사업내용' 라벨")


if __name__ == "__main__":
    unittest.main(verbosity=2)
