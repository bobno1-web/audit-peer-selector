#!/usr/bin/env python3
"""임베딩/벡터 캐시 계약 테스트 (Loop 3 PART 0, api-budget 강제).

실증:
  1. 같은 키를 두 번 요청하면 두 번째는 벡터화(취득) 호출이 **0** (캐시 히트).
  2. 캐시 파일이 있으면 **재실행**(새 프로세스 흉내)에도 호출 0.
  3. 벡터라이저 **버전**이 바뀌면 캐시 분리(재계산) — 구캐시 오염 없음.
비용 폭발을 코드가 막는다.
"""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vector_cache as vc                                # noqa: E402


class Counter:
    def __init__(self):
        self.calls = 0

    def vectorize(self, items):
        self.calls += 1
        mat = np.array([[float(len(str(t)))] for _, t in items], dtype=np.float32)
        return mat, {"dim": 1}


ITEMS = [("00000001", "사업의 내용 가나다"), ("00000002", "제조업 반도체"), ("00000003", "서비스")]


class TestEmbeddingCache(unittest.TestCase):
    def test_second_request_zero_calls(self):
        with tempfile.TemporaryDirectory() as d:
            npz = Path(d) / "vec.npz"
            c = Counter()
            _, _, _, hit1 = vc.build_or_load(npz, ITEMS, "v1", c.vectorize)
            self.assertFalse(hit1, "첫 요청은 캐시 미스여야")
            self.assertEqual(c.calls, 1, "첫 요청은 벡터화 1회")
            _, _, _, hit2 = vc.build_or_load(npz, ITEMS, "v1", c.vectorize)
            self.assertTrue(hit2, "같은 키 두 번째는 캐시 히트여야")
            self.assertEqual(c.calls, 1, "★ 두 번째 요청은 벡터화 호출 0 이어야 한다")

    def test_persisted_cache_zero_calls_new_run(self):
        with tempfile.TemporaryDirectory() as d:
            npz = Path(d) / "vec.npz"
            vc.build_or_load(npz, ITEMS, "v1", Counter().vectorize)      # 파일 생성
            self.assertTrue(npz.exists())
            fresh = Counter()                                           # 새 프로세스 흉내
            _, _, _, hit = vc.build_or_load(npz, ITEMS, "v1", fresh.vectorize)
            self.assertTrue(hit)
            self.assertEqual(fresh.calls, 0, "★ 캐시 파일 존재 시 재실행 호출 0")

    def test_version_bump_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            npz = Path(d) / "vec.npz"
            vc.build_or_load(npz, ITEMS, "v1", Counter().vectorize)
            c = Counter()
            _, _, _, hit = vc.build_or_load(npz, ITEMS, "v2", c.vectorize)   # 버전 변경
            self.assertFalse(hit, "버전이 바뀌면 캐시 미스(재계산)")
            self.assertEqual(c.calls, 1)

    def test_content_change_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            npz = Path(d) / "vec.npz"
            vc.build_or_load(npz, ITEMS, "v1", Counter().vectorize)
            changed = ITEMS[:-1] + [("00000003", "완전히 다른 텍스트")]
            c = Counter()
            _, _, _, hit = vc.build_or_load(npz, changed, "v1", c.vectorize)
            self.assertFalse(hit, "콘텐츠가 바뀌면 캐시 미스")
            self.assertEqual(c.calls, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
