#!/usr/bin/env python3
"""임베딩/벡터 캐시 원시자 (Loop 3 PART 0, api-budget 계약).

캐시 키 = (콘텐츠, 벡터라이저 버전)의 해시. 소스·버전이 바뀌면 키가 바뀌어 새 캐시로 분리.
build_or_load: 캐시 히트면 vectorize_fn 을 **호출하지 않는다**(취득/벡터화 0). 미스면 계산·저장.
★ 이 계약을 tests/test_embedding_cache.py 가 카운터로 실증한다.
"""
import hashlib
from pathlib import Path

import numpy as np


def content_hash(items, version):
    """items: [(key, text), ...]. 정렬 후 콘텐츠+버전을 SHA-256 해시."""
    h = hashlib.sha256()
    h.update(str(version).encode("utf-8"))
    for k, t in sorted(items, key=lambda x: str(x[0])):
        h.update(b"\x00")
        h.update(str(k).encode("utf-8"))
        h.update(b"\x01")
        h.update(str(t).encode("utf-8"))
    return h.hexdigest()


def build_or_load(npz_path, items, version, vectorize_fn):
    """캐시 히트(해시 일치)면 (matrix, keys, meta, True) 반환하고 vectorize_fn 미호출.
    미스면 vectorize_fn(items) 호출 → 저장 → (…, False).

    vectorize_fn(items) 은 (matrix: np.ndarray, extra: dict) 를 반환해야 한다.
    """
    npz_path = Path(npz_path)
    key = content_hash(items, version)
    keys = [str(k) for k, _ in items]
    if npz_path.exists():
        z = np.load(npz_path, allow_pickle=True)
        if str(z["meta_hash"]) == key:                        # ★ 히트: 계산 없음
            return z["matrix"], [str(c) for c in z["keys"]], dict(z.get("meta", np.array({})).item()
                                                                   if "meta" in z else {}), True
    matrix, extra = vectorize_fn(items)                       # ★ 미스: 계산
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_path, matrix=matrix, keys=np.array(keys),
                        meta_hash=key, meta=np.array(extra, dtype=object))
    return matrix, keys, extra, False
