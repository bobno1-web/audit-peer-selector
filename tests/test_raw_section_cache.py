#!/usr/bin/env python3
"""raw 섹션 캐시 계약 테스트 (Loop 5 PART 0, api-budget 강제 — 검증방 Loop4 지적 #2 상환).

실증:
  1. 같은 키 두 번째 요청 → 취득(producer) 호출 0 (캐시 히트).
  2. 캐시 파일이 있으면 재실행(새 프로세스 흉내)에도 호출 0.
  3. rcept_no(문서) 또는 version(추출기) 이 바뀌면 캐시 분리(재취득) — 구캐시 오염 없음.
  4. 020(limit)·transient(error) 는 캐시하지 않는다(다음 실행 재시도 가능).
  5. raw span 왕복: 캐시된 raw span(표 구조 보존)을 다시 파서에 넣으면 동일 프로필.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import raw_section_cache as rc                             # noqa: E402
import segment_parser as sg                                # noqa: E402

SECTION = "사업의 내용"
_TABLE = ("<TABLE><TR><TD>사업부문</TD><TD>매출액</TD><TD>비율</TD></TR>"
          "<TR><TD>반도체</TD><TD>1,000,000</TD><TD>50.0</TD></TR>"
          "<TR><TD>가전</TD><TD>1,000,000</TD><TD>50.0</TD></TR></TABLE>")
_DOC = ("<TITLE>I. 회사의 개요</TITLE><SPAN>개요</SPAN>"
        "<TITLE>II. 사업의 내용</TITLE>" + _TABLE +
        "<TITLE>III. 재무에 관한 사항</TITLE><SPAN>재무</SPAN>")


class Producer:
    """document.xml 취득을 흉내내는 카운터. 호출 시 raw span 을 추출해 반환."""
    def __init__(self, doc=_DOC, status="ok"):
        self.calls = 0
        self.doc = doc
        self.status = status

    def __call__(self):
        self.calls += 1
        if self.status != "ok":
            return None, self.status
        return sg.raw_section_span(self.doc, SECTION), "ok"


class TestRawSectionCache(unittest.TestCase):
    def test_second_request_zero_calls(self):
        with tempfile.TemporaryDirectory() as d:
            p = Producer()
            sec1, out1 = rc.get_or_fetch(d, "00000001", "R1", SECTION, p)
            self.assertEqual(out1, "miss_fetched")
            self.assertEqual(p.calls, 1)
            sec2, out2 = rc.get_or_fetch(d, "00000001", "R1", SECTION, p)
            self.assertEqual(out2, "hit")
            self.assertEqual(p.calls, 1, "★ 두 번째 요청은 취득 호출 0 이어야 한다")
            self.assertEqual(sec1, sec2)

    def test_persisted_cache_zero_calls_new_run(self):
        with tempfile.TemporaryDirectory() as d:
            rc.get_or_fetch(d, "00000001", "R1", SECTION, Producer())      # 파일 생성
            fresh = Producer()                                             # 새 프로세스 흉내
            _, out = rc.get_or_fetch(d, "00000001", "R1", SECTION, fresh)
            self.assertEqual(out, "hit")
            self.assertEqual(fresh.calls, 0, "★ 캐시 파일 존재 시 재실행 호출 0")

    def test_document_change_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            rc.get_or_fetch(d, "00000001", "R1", SECTION, Producer())
            p = Producer()
            _, out = rc.get_or_fetch(d, "00000001", "R2", SECTION, p)      # 다른 문서(rcept_no)
            self.assertEqual(out, "miss_fetched")
            self.assertEqual(p.calls, 1, "다른 문서면 캐시 미스(재취득)")

    def test_version_bump_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            rc.get_or_fetch(d, "00000001", "R1", SECTION, Producer(), version="1")
            p = Producer()
            _, out = rc.get_or_fetch(d, "00000001", "R1", SECTION, p, version="2")
            self.assertEqual(out, "miss_fetched")
            self.assertEqual(p.calls, 1, "추출기 버전이 바뀌면 캐시 미스")

    def test_limit_and_error_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            lim = Producer(status="limit")
            sec, out = rc.get_or_fetch(d, "00000001", "R1", SECTION, lim)
            self.assertEqual(out, "limit")
            self.assertIsNone(sec)
            # 020 후 재실행: 캐시 안 됐으므로 다시 취득 시도(이번엔 성공)
            ok = Producer()
            sec2, out2 = rc.get_or_fetch(d, "00000001", "R1", SECTION, ok)
            self.assertEqual(out2, "miss_fetched", "★ limit 는 캐시하지 않아 재시도된다")
            self.assertEqual(ok.calls, 1)

    def test_empty_section_is_cached(self):
        # 문서는 받았으나 '사업의 내용' 섹션이 없으면 "" 를 캐시(재취득 방지) — 재시도 아님.
        with tempfile.TemporaryDirectory() as d:
            noSec = Producer(doc="<P>섹션 없는 문서</P>")
            sec, out = rc.get_or_fetch(d, "00000001", "R1", SECTION, noSec)
            self.assertEqual(out, "miss_fetched")
            self.assertEqual(sec, "")                                      # 섹션 부재 = 빈 캐시
            again = Producer(doc="<P>섹션 없는 문서</P>")
            _, out2 = rc.get_or_fetch(d, "00000001", "R1", SECTION, again)
            self.assertEqual(out2, "hit")
            self.assertEqual(again.calls, 0, "섹션 부재도 캐시 → 재취득 0")

    def test_cached_span_roundtrip(self):
        # 캐시된 raw span(표 구조 보존)을 다시 파서에 넣으면 원문과 동일한 프로필.
        with tempfile.TemporaryDirectory() as d:
            span, _ = rc.get_or_fetch(d, "00000001", "R1", SECTION, Producer())
            prof_span, st_span = sg.segment_shares(span, SECTION)
            prof_doc, st_doc = sg.segment_shares(_DOC, SECTION)
            self.assertEqual(st_span, "ok")
            self.assertEqual(prof_span, prof_doc, "★ 캐시 span 재파싱 = 원문 파싱(표 구조 보존)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
