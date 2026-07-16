#!/usr/bin/env python3
"""raw 섹션 캐시 (Loop 5 PART 0, api-budget 계약 상환 — 검증방 Loop4 지적 #2).

Loop 3/4 는 '사업의 내용' 섹션을 **flatten 텍스트로만** 캐시해 <TABLE> 구조를 버렸다.
그 결과 부문별 매출표(raw 구조 필수)를 캐시에서 복원하지 못하고, 020 리셋마다 document.xml 을
재취득해야 했다(SEGMENT_EXTRACTION.md 실증). 이 캐시는 섹션의 **raw span(표 구조 보존)** 을
디스크에 저장한다 → 다음 실행부터 재취득 0(캐시 히트면 producer 미호출).

캐시 키 = (corp_code, rcept_no, section, version) 의 SHA-256.
  - rcept_no = 문서(콘텐츠) 식별자. 다른 filing 이면 키가 바뀌어 새 캐시로 분리(구캐시 오염 없음).
  - version = 섹션 span 추출기 버전. 추출 구조가 바뀌면 키가 바뀌어 재추출.
  - ★ '섹션만' 저장(전문 아님, api-budget 규칙 3). 파일 존재 = 히트(sidecar 불요).
저장: cache_dir/<key>.txt.gz (gzip).

계약(tests/test_raw_section_cache.py 가 카운터로 실증):
  1. 같은 키 두 번째 요청 → producer 호출 0.  2. 캐시 파일 존재 시 재실행(새 프로세스) 호출 0.
  3. rcept_no·version 변경 → 캐시 분리(재취득).  4. 020/transient 는 캐시 안 함(다음 실행 재시도).
"""
import gzip
import hashlib
from pathlib import Path

# 섹션 span 추출기 버전(segment_parser._section_span 구조). 구조 변경 시 bump → 캐시 자동 분리.
SECTION_EXTRACTOR_VERSION = "1"


def cache_key(corp_code, rcept_no, section_title, version=SECTION_EXTRACTOR_VERSION):
    """(기업, 문서, 섹션소스, 버전) 해시 — api-budget 규칙 2(콘텐츠·구성 해시)."""
    h = hashlib.sha256()
    for part in (corp_code, rcept_no, section_title, version):
        h.update(b"\x00")
        h.update(str(part).encode("utf-8"))
    return h.hexdigest()


def load(cache_dir, key):
    """캐시 히트면 섹션 텍스트(str, 빈 문자열 가능) 반환, 미스면 None."""
    p = Path(cache_dir) / f"{key}.txt.gz"
    if p.exists():
        return gzip.decompress(p.read_bytes()).decode("utf-8")
    return None


def save(cache_dir, key, text):
    p = Path(cache_dir) / f"{key}.txt.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress((text or "").encode("utf-8")))


def get_or_fetch(cache_dir, corp_code, rcept_no, section_title, producer,
                 version=SECTION_EXTRACTOR_VERSION):
    """반환 (section_text|None, outcome).

    outcome ∈ {"hit", "miss_fetched", "limit", "error"}.
      - "hit": 캐시에서 반환(producer 미호출).
      - "miss_fetched": producer 로 취득해 저장(section_text 는 "" 일 수 있음 = 섹션 부재).
      - "limit"/"error": producer 가 취득 실패 → **캐시 안 함**(다음 실행 재시도), section_text=None.

    producer() 은 (section_text:str|None, status) 를 반환:
      status=="ok" → section_text(str, "" 가능) 를 캐시. 그 외("limit","error") → 캐시 안 함.
    """
    key = cache_key(corp_code, rcept_no, section_title, version)
    cached = load(cache_dir, key)
    if cached is not None:
        return cached, "hit"
    section, status = producer()
    if status == "ok":
        save(cache_dir, key, section or "")
        return section or "", "miss_fetched"
    return None, status
