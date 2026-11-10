"""Lightweight lexical retrieval (BM25) over stored document segments.

A vector database can replace this behind the same function signature; BM25 is used first
because it is dependency-free, deterministic and easy to audit.
"""
from __future__ import annotations

import math
import re
from collections import Counter

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("the a an and or of to in on for is are was were be been with that this it as at by from we our you".split())


def tokenize(s: str) -> list[str]:
    return [t for t in TOKEN.findall(s.lower()) if t not in STOP]


def bm25(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    toks = [tokenize(d) for d in docs]
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(t) for t in toks) / n or 1
    df = Counter(w for t in toks for w in set(t))
    q = tokenize(query)
    scores = []
    for t in toks:
        tf = Counter(t)
        s = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avgdl))
        scores.append(s)
    return scores
