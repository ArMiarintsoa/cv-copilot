"""Métriques d'évaluation (sans dépendance lourde)."""
from __future__ import annotations

import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, cid in enumerate(retrieved, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def coverage(expected_facts: list[str], cv_text: str) -> float:
    """Part des faits importants (annotés à la main) retrouvés dans le CV (insensible à la casse)."""
    if not expected_facts:
        return 1.0
    low = cv_text.lower()
    return sum(f.lower() in low for f in expected_facts) / len(expected_facts)
