#!/usr/bin/env python3
"""부문별 매출 파서 논리 검증 (Loop 4 PART 1) — 합성 DART 서식 표로 실증.

라이브 문서 취득(document.xml)은 020 일한도로 블록이지만, **파싱 논리 자체**는 서식 구조를 아는
합성 표로 검증 가능하다(라이브 커버리지만 quota 대기). 검증 항목:
  - 다부문 표 → 집중도 프로필(부문수·최대비중·HHI) 정확.
  - 합계/소계 행 제외.
  - 행 내 '비율'(퍼센트)은 매출로 오인하지 않음(콤마그룹/4자리+만 화폐성).
  - 부문표 없음/섹션 없음 → 결측(None) (임의대체 0).
  - ★ 프로필은 '매출 비중' 파생 스칼라만 — '이익률' 필드 없음(채점비율 누출 차단).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import segment_parser as sg                              # noqa: E402

SECTION = "사업의 내용"


def _doc(table_xml):
    return ("<TITLE>I. 회사의 개요</TITLE><SPAN>개요</SPAN>"
            "<TITLE>II. 사업의 내용</TITLE>" + table_xml +
            "<TITLE>III. 재무에 관한 사항</TITLE><SPAN>재무</SPAN>")


MULTI = """<TABLE>
<TR><TD>사업부문</TD><TD>품목</TD><TD>매출액</TD><TD>비율</TD></TR>
<TR><TD>반도체</TD><TD>메모리</TD><TD>1,000,000</TD><TD>50.0</TD></TR>
<TR><TD>디스플레이</TD><TD>패널</TD><TD>600,000</TD><TD>30.0</TD></TR>
<TR><TD>가전</TD><TD>TV</TD><TD>400,000</TD><TD>20.0</TD></TR>
<TR><TD>합계</TD><TD>-</TD><TD>2,000,000</TD><TD>100.0</TD></TR>
</TABLE>"""

SINGLE = """<TABLE>
<TR><TD>사업부문</TD><TD>매출액</TD><TD>비중</TD></TR>
<TR><TD>단일제품</TD><TD>5,000,000</TD><TD>100.0</TD></TR>
</TABLE>"""

NOTABLE = """<TABLE>
<TR><TD>구분</TD><TD>임직원수</TD></TR>
<TR><TD>정규직</TD><TD>123</TD></TR>
</TABLE>"""


class TestSegmentParser(unittest.TestCase):
    def test_multi_segment_profile(self):
        prof, status = sg.segment_shares(_doc(MULTI), SECTION)
        self.assertEqual(status, "ok")
        self.assertEqual(prof["seg_n"], 3)                          # 합계 행 제외
        self.assertAlmostEqual(prof["seg_top_share"], 0.5, places=4)
        self.assertAlmostEqual(prof["seg_hhi"], 0.25 + 0.09 + 0.04, places=4)

    def test_percent_not_counted_as_revenue(self):
        # 비율 컬럼(50.0 등)은 화폐성으로 안 잡혀 매출로 오인되지 않아야 정확한 share 가 나온다
        prof, _ = sg.segment_shares(_doc(MULTI), SECTION)
        self.assertEqual(prof["seg_n"], 3)                          # 4행(4비율값)이 아니라 3부문

    def test_single_segment(self):
        prof, status = sg.segment_shares(_doc(SINGLE), SECTION)
        self.assertEqual(status, "ok")
        self.assertEqual(prof["seg_n"], 1)
        self.assertAlmostEqual(prof["seg_top_share"], 1.0)
        self.assertAlmostEqual(prof["seg_hhi"], 1.0)

    def test_no_segment_table_is_missing(self):
        prof, status = sg.segment_shares(_doc(NOTABLE), SECTION)
        self.assertIsNone(prof)                                     # 임의대체 0
        self.assertEqual(status, "no_table")

    def test_no_section_is_missing(self):
        prof, status = sg.segment_shares("<P>제목없는 원문</P>", SECTION)
        self.assertIsNone(prof)
        self.assertEqual(status, "no_section")

    def test_profile_has_no_profit_field(self):
        # ★ 부문 '이익률'은 절대 산출하지 않는다(채점비율 누출 차단) — 프로필 키는 비중 파생뿐
        prof, _ = sg.segment_shares(_doc(MULTI), SECTION)
        self.assertEqual(set(prof), {"seg_n", "seg_top_share", "seg_hhi"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
