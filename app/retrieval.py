"""Retrieval par section du CV : requêtes ciblées + mots-clés de l'offre + rerank optionnel."""
from __future__ import annotations

from functools import lru_cache

from app import indexing
from app.config import settings
from app.schemas import JobOffer

# section du CV -> (requête de base, types de chunks autorisés, top-k)
SECTION_SPECS: dict[str, dict] = {
    "identite": {"query": "nom prénom email téléphone adresse LinkedIn GitHub contact", "types": ["identite"], "k": 3},
    "resume": {"query": "profil résumé objectif professionnel présentation", "types": ["resume", "identite"], "k": 3},
    "experiences": {"query": "expérience professionnelle poste entreprise missions réalisations", "types": ["experience"], "k": 10},
    "formations": {"query": "formation diplôme école université études", "types": ["formation"], "k": 6},
    "certifications": {"query": "certification certificat licence", "types": ["certifications"], "k": 5},
    "competences": {"query": "compétences techniques outils technologies", "types": None, "k": 8},
    "langues": {"query": "langues niveau anglais français", "types": ["langues", "competences"], "k": 3},
    "projets": {"query": "projet personnel académique réalisation technologies", "types": ["projets"], "k": 6},
}


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.reranker_model)


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    if not settings.use_reranker or len(candidates) <= 1:
        return candidates
    scores = _reranker().predict([(query, c["text"]) for c in candidates])
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)


def retrieve_for_section(session_id: str, section: str, offer: JobOffer | None = None) -> list[dict]:
    spec = SECTION_SPECS[section]
    queries = [spec["query"]]
    if offer and section in {"experiences", "competences", "projets", "resume"}:
        keywords = (offer.competences_requises + offer.mots_cles)[:5]
        queries += [f"{spec['query']} {kw}" for kw in keywords]
        if offer.titre:
            queries.append(f"{spec['query']} {offer.titre}")
    results = indexing.query(session_id, queries, spec["k"], spec["types"])
    if not results and spec["types"]:  # repli sans filtre de type
        results = indexing.query(session_id, queries, spec["k"])
    rank_query = spec["query"] + (f" {offer.titre}" if offer and offer.titre else "")
    return rerank(rank_query, results)[: spec["k"]]


def retrieve_all(session_id: str, offer: JobOffer | None = None) -> dict[str, list[dict]]:
    return {s: retrieve_for_section(session_id, s, offer) for s in SECTION_SPECS}
