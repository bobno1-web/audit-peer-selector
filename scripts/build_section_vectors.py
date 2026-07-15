#!/usr/bin/env python3
"""'사업의 내용' 섹션 텍스트 → 문자 n-gram TF-IDF 벡터 캐시 (Loop 3 PART 1).

★ Loop 2와의 유일한 차이 = **입력 텍스트 소스**. 벡터라이저(문자 3-gram TF-IDF, vocab 3000,
  L2정규화)는 Loop 2(build_text_vectors)와 동일 — 한 변수(전문 vs 섹션)만 바꿔 효과를 격리한다.
★ 캐시: (콘텐츠, 벡터라이저버전) 해시(vector_cache). 재실행 시 해시 일치면 재계산 0.
입력: section_text.parquet(status=='ok'만). 출력: section_vectors.npz(matrix, keys, meta_hash).
"""
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vector_cache as vc                                # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "data" / "pit" / "features" / "business"
SECTXT = B / "section_text.parquet"
OUTNPZ = B / "section_vectors.npz"
CONFIG = ROOT / "config" / "default.yaml"
NON = re.compile(r"[0-9\W]+")                             # 숫자·기호 제거(Loop 2와 동일)
VERSION = "charngram-tfidf-v1"                            # 벡터라이저 버전(바뀌면 캐시 분리)


def ngrams(text, n):
    t = NON.sub("", text)
    return [t[i:i + n] for i in range(len(t) - n + 1)] if len(t) >= n else []


def make_vectorizer(n, vocab_size):
    def vectorize(items):
        docs = [ngrams(str(t), n) for _, t in items]
        doc_freq = Counter()
        for g in docs:
            doc_freq.update(set(g))
        vocab = [w for w, _ in doc_freq.most_common(vocab_size)]
        vidx = {w: i for i, w in enumerate(vocab)}
        N = len(docs)
        idf = np.array([np.log(N / doc_freq[w]) for w in vocab]) if vocab else np.zeros(0)
        mat = np.zeros((N, len(vocab)), dtype=np.float32)
        for r, g in enumerate(docs):
            for w, cnt in Counter(g).items():
                j = vidx.get(w)
                if j is not None:
                    mat[r, j] = cnt
        mat = mat * idf
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        mat = np.divide(mat, norms, out=np.zeros_like(mat), where=norms > 0)
        return mat, {"vocab_size": len(vocab), "ngram": n}
    return vectorize


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["similarity"]
    n, vocab_size = int(cfg["text_ngram"]), int(cfg["text_vocab_size"])
    df = pd.read_parquet(SECTXT)
    df = df[(df["status"] == "ok") & (df["section_text"].astype(str).str.len() > 0)].reset_index(drop=True)
    items = list(zip(df["corp_code"].astype(str), df["section_text"].astype(str)))
    version = f"{VERSION}|ngram={n}|vocab={vocab_size}"
    mat, keys, meta, from_cache = vc.build_or_load(OUTNPZ, items, version, make_vectorizer(n, vocab_size))
    print(f"section_vectors: {mat.shape} keys={len(keys)} from_cache={from_cache} meta={meta} "
          f"→ {OUTNPZ}", file=sys.stderr)


if __name__ == "__main__":
    main()
