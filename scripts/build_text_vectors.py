#!/usr/bin/env python3
"""사업내용 텍스트 → 문자 n-gram TF-IDF 벡터 캐시 (Loop 2, sklearn 부재로 numpy 자작).

business_text.parquet(earliest dev 원문, point-in-time 안전) → L2정규화 TF-IDF 행렬.
캐시: data/pit/features/business/text_vectors.npz (matrix, corp_codes, vocab).
★ 임베딩 캐싱(한 번만 계산). 코사인 유사도 = 정규화 벡터 내적.
"""
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "data" / "pit" / "features" / "business"
CONFIG = ROOT / "config" / "default.yaml"
NON = re.compile(r"[0-9\W]+")                           # 숫자·기호 제거(재무숫자 노이즈 억제)


def ngrams(text, n):
    t = NON.sub("", text)
    return [t[i:i + n] for i in range(len(t) - n + 1)] if len(t) >= n else []


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["similarity"]
    n, vocab_size = int(cfg["text_ngram"]), int(cfg["text_vocab_size"])
    df = pd.read_parquet(B / "business_text.parquet")
    df = df[df["text"].astype(str).str.len() > 0].reset_index(drop=True)
    docs = [ngrams(str(t), n) for t in df["text"]]
    # df(문서빈도) 상위 vocab_size 어휘
    doc_freq = Counter()
    for g in docs:
        doc_freq.update(set(g))
    vocab = [w for w, _ in doc_freq.most_common(vocab_size)]
    vidx = {w: i for i, w in enumerate(vocab)}
    N = len(docs)
    idf = np.array([np.log(N / doc_freq[w]) for w in vocab])
    mat = np.zeros((N, len(vocab)), dtype=np.float32)
    for r, g in enumerate(docs):
        c = Counter(g)
        for w, cnt in c.items():
            j = vidx.get(w)
            if j is not None:
                mat[r, j] = cnt
    mat = mat * idf                                      # tf-idf
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = np.divide(mat, norms, out=np.zeros_like(mat), where=norms > 0)
    np.savez_compressed(B / "text_vectors.npz",
                        matrix=mat, corp_codes=df["corp_code"].to_numpy(),
                        vocab=np.array(vocab))
    print(f"text_vectors: {N} docs × {len(vocab)} ngrams → {B/'text_vectors.npz'}", file=sys.stderr)


if __name__ == "__main__":
    main()
