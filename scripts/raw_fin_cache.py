#!/usr/bin/env python3
"""raw 재무제표 캐시 (Loop 6 PART 0, api-budget 계약 상환).

지금까지 pit_build / pit_build_full 은 fnlttSinglAcntAll 응답을 **캐시하지 않고** 매번 재취득했다.
그래서 별칭·resolver 를 고쳐 targets 를 재생성하려면 전 유니버스를 다시 호출해야 했다(비용 폭발).
이 캐시는 fnlttSinglAcntAll 의 **raw list 행**(계정별 원본 행)을 디스크에 저장한다 → 다음 재생성부터
재취득 0(캐시 히트면 API 미호출). raw_section_cache 와 같은 계약.

캐시 키 = (corp_code, bsns_year, reprt_code, fs_div, version) 의 SHA-256.
  - (기업, 회계연도, 보고서종류, 개별/연결) = 응답을 유일하게 식별.
  - version = raw 응답 스키마 버전(행 필드 구성). 소스가 바뀌면 키가 바뀌어 새 캐시로 분리.
  - status=="000"(정상)만 캐시. 020(한도)/013(무자료)/ERR 은 캐시 안 함 → 다음 실행 재시도(020),
    단 013(그 fs_div 에 자료 없음)은 '빈 리스트'로 캐시(정상 부재; 재호출 낭비 방지).
저장: cache_dir/<key>.json.gz (gzip JSON list).

계약(tests/test_raw_fin_cache.py 가 카운터로 실증):
  1. 같은 키 두 번째 요청 → fetch 0.  2. 캐시 파일 존재 시 재실행 호출 0.
  3. fs_div/연도/버전 변경 → 캐시 분리.  4. 020/ERR 은 캐시 안 함(재시도).  5. 013(무자료) 은 빈리스트 캐시.
"""
import gzip
import hashlib
import json
from pathlib import Path

# raw list 스키마 버전(계정 행 필드). 구조 변경 시 bump → 캐시 자동 분리.
RAW_FIN_VERSION = "1"


def cache_key(corp_code, bsns_year, reprt_code, fs_div, version=RAW_FIN_VERSION):
    """(기업, 회계연도, 보고서, 개별/연결, 버전) 해시 — api-budget 규칙 2(콘텐츠·구성 해시)."""
    h = hashlib.sha256()
    for part in (corp_code, bsns_year, reprt_code, fs_div, version):
        h.update(b"\x00")
        h.update(str(part).encode("utf-8"))
    return h.hexdigest()


def load(cache_dir, key):
    """캐시 히트면 list(행들, 빈 리스트 가능) 반환, 미스면 None."""
    p = Path(cache_dir) / f"{key}.json.gz"
    if p.exists():
        return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
    return None


def save(cache_dir, key, rows):
    p = Path(cache_dir) / f"{key}.json.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(rows or [], ensure_ascii=False).encode("utf-8")))


def get_or_fetch(cache_dir, corp_code, bsns_year, reprt_code, fs_div, producer,
                 version=RAW_FIN_VERSION):
    """반환 (rows|None, outcome).

    outcome ∈ {"hit", "miss_fetched", "empty_cached", "limit", "error"}.
      - "hit": 캐시에서 반환(producer 미호출).
      - "miss_fetched": producer 로 취득해 저장(정상 000, 행 있음).
      - "empty_cached": producer 가 013(무자료) → 빈 리스트로 캐시(정상 부재; 재호출 낭비 방지).
      - "limit"/"error": producer 실패 → **캐시 안 함**(다음 실행 재시도), rows=None.

    producer() 은 (rows:list|None, status) 를 반환:
      status=="000" → rows 캐시. status=="013" → 빈 리스트 캐시. 그 외("020","ERR"...) → 캐시 안 함.
    """
    key = cache_key(corp_code, bsns_year, reprt_code, fs_div, version)
    cached = load(cache_dir, key)
    if cached is not None:
        return cached, "hit"
    rows, status = producer()
    if status == "000":
        save(cache_dir, key, rows or [])
        return rows or [], "miss_fetched"
    if status == "013":                       # 그 fs_div 에 자료 없음 = 정상 부재 → 빈리스트 캐시
        save(cache_dir, key, [])
        return [], "empty_cached"
    return None, "limit" if status == "020" else "error"
