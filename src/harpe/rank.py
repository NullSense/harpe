"""Rank candidates by relevance (query-token overlap) first, then resolution."""
import re

from .models import Candidate

STOP = {"the", "and", "of", "his", "her", "its", "from", "with", "for", "are",
        "was", "painting", "original"}


def tokens(q: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", q.lower())
            if len(t) >= 3 and t not in STOP]


def rank(q: str, cands: list[Candidate]) -> list[Candidate]:
    """Most relevant first, biggest scan of each work first, deduped by source URL.

    A relevance floor trims noise only on a strong (>=4 query-token) match — weak
    queries keep everything so a one-word search still shows results.
    """
    toks = tokens(q)
    scored = []
    for c in cands:
        hay = f"{c.title} {c.artist}".lower()
        rel = sum(1 for t in toks if t in hay)
        scored.append((rel, c))
    scored.sort(key=lambda x: (x[0], x[1].area), reverse=True)
    if not scored:
        return []
    max_rel = scored[0][0]
    floor = 2 if max_rel >= 4 else 0
    seen, out = set(), []
    for rel, c in scored:
        if rel < floor:
            continue
        key = c.spec or c.thumb
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
