#!/usr/bin/env python3
"""raw 재무제표 캐시 계약 테스트 (Loop 6 PART 0, api-budget 강제).

실증:
  1. 같은 키 두 번째 요청 → 취득(producer) 호출 0 (캐시 히트).
  2. 캐시 파일이 있으면 재실행(새 프로세스 흉내)에도 호출 0.
  3. bsns_year·fs_div·version 이 바뀌면 캐시 분리(재취득) — 구캐시 오염 없음.
  4. 020(limit)·ERR 은 캐시하지 않는다(다음 실행 재시도 가능).
  5. 013(무자료) 은 빈 리스트로 캐시(정상 부재; 재호출 낭비 방지).
  6. rows 왕복: 캐시된 raw list 를 다시 resolver 에 넣으면 동일 값.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import raw_fin_cache as rfc                                  # noqa: E402
import pit_build as pb                                       # noqa: E402

REPRT = "11011"
_ROWS = [
    {"sj_div": "BS", "account_nm": "매출채권 및 기타유동채권",
     "account_id": "ifrs-full_TradeAndOtherCurrentReceivables", "thstrm_amount": "12,840,776,999",
     "rcept_no": "20200401000001"},
    {"sj_div": "BS", "account_nm": "매출채권", "account_id": "dart_ShortTermTradeReceivable",
     "thstrm_amount": "11,702,295,937", "rcept_no": "20200401000001"},
    {"sj_div": "IS", "account_nm": "매출액", "account_id": "ifrs-full_Revenue",
     "thstrm_amount": "74,989,866,585", "rcept_no": "20200401000001"},
]


class Producer:
    """fnlttSinglAcntAll 취득을 흉내내는 카운터."""
    def __init__(self, rows=None, status="000"):
        self.calls = 0
        self.rows = _ROWS if rows is None else rows
        self.status = status

    def __call__(self):
        self.calls += 1
        if self.status != "000":
            return None, self.status
        return self.rows, "000"


class TestRawFinCache(unittest.TestCase):
    def test_second_request_zero_calls(self):
        with tempfile.TemporaryDirectory() as d:
            p = Producer()
            r1, o1 = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", p)
            self.assertEqual(o1, "miss_fetched")
            self.assertEqual(p.calls, 1)
            r2, o2 = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", p)
            self.assertEqual(o2, "hit")
            self.assertEqual(p.calls, 1, "★ 두 번째 요청은 취득 호출 0")
            self.assertEqual(r1, r2)

    def test_persisted_cache_zero_calls_new_run(self):
        with tempfile.TemporaryDirectory() as d:
            rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", Producer())
            fresh = Producer()
            _, out = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", fresh)
            self.assertEqual(out, "hit")
            self.assertEqual(fresh.calls, 0, "★ 캐시 파일 존재 시 재실행 호출 0")

    def test_year_and_fsdiv_and_version_invalidate(self):
        with tempfile.TemporaryDirectory() as d:
            rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", Producer())
            for kw in ({"bsns_year": "2018"}, {"fs_div": "CFS"}):
                p = Producer()
                args = dict(corp_code="00141389", bsns_year="2019", reprt_code=REPRT, fs_div="OFS")
                args.update(kw)
                _, out = rfc.get_or_fetch(d, args["corp_code"], args["bsns_year"], args["reprt_code"],
                                          args["fs_div"], p)
                self.assertEqual(out, "miss_fetched", f"{kw} 변경 시 캐시 미스")
                self.assertEqual(p.calls, 1)
            pv = Producer()
            _, outv = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", pv, version="2")
            self.assertEqual(outv, "miss_fetched", "version 변경 시 캐시 미스")

    def test_limit_and_error_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            lim = Producer(status="020")
            rows, out = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", lim)
            self.assertEqual(out, "limit")
            self.assertIsNone(rows)
            ok = Producer()
            _, out2 = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", ok)
            self.assertEqual(out2, "miss_fetched", "★ 020 은 캐시 안 함 → 재시도")
            self.assertEqual(ok.calls, 1)

    def test_no_data_013_cached_empty(self):
        with tempfile.TemporaryDirectory() as d:
            nod = Producer(status="013")
            rows, out = rfc.get_or_fetch(d, "00000001", "2019", REPRT, "OFS", nod)
            self.assertEqual(out, "empty_cached")
            self.assertEqual(rows, [])
            again = Producer(status="013")
            _, out2 = rfc.get_or_fetch(d, "00000001", "2019", REPRT, "OFS", again)
            self.assertEqual(out2, "hit")
            self.assertEqual(again.calls, 0, "013 무자료도 빈리스트 캐시 → 재취득 0")

    def test_cached_rows_roundtrip_pure_receivable(self):
        # ★ 캐시된 raw rows 를 교정 resolver 에 넣으면 순수 매출채권(11.70B) 채택(합산 12.84B 아님).
        with tempfile.TemporaryDirectory() as d:
            rows, _ = rfc.get_or_fetch(d, "00141389", "2019", REPRT, "OFS", Producer())
            vals = pb.extract(rows)
            self.assertEqual(vals["매출채권"], 11702295937,
                             "★ 별칭 우선순위: 순수 매출채권 채택(합산 아님)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
