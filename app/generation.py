"""Génération du CV : analyse de l'offre -> retrieval par section -> LLM (JSON) -> validation -> fact-check."""
from __future__ import annotations

import json

from app import indexing, llm
from app.retrieval import retrieve_all
from app.schemas import CV, NON_RENSEIGNE, GenerationResult, JobOffer
from app.verification import check_identity, clean_non_renseigne, drop_unknown_sources, fact_check

OFFER_SYSTEM = (
    "Tu analyses des offres d'emploi. Extrais uniquement ce qui est écrit dans l'offre. "
    "Réponds uniquement en JSON."
)
OFFER_SCHEMA = (
    '{"titre": "", "entreprise": "", "competences_requises": [], "mots_cles": [], "responsabilites": []}'
)

CV_SYSTEM = f"""Tu es un assistant de rédaction de CV. Tu reformules des faits ; tu n'inventes RIEN.

RÈGLES ABSOLUES
1. N'utilise QUE le contexte fourni (extraits numérotés par identifiant). Si une information n'y figure pas, écris « {NON_RENSEIGNE} » (ou laisse la liste vide).
2. Chaque réalisation, formation, projet, certification, compétence et langue doit citer le `source_id` de l'extrait dont elle provient. Cite exactement les identifiants fournis.
3. Ne jamais embellir : pas de chiffres, durées, niveaux, responsabilités, outils ou diplômes absents des extraits. Pas de verbes plus forts que les sources (ne transforme pas « participé » en « dirigé »).
4. Tu peux reformuler, réordonner et mettre en avant ce qui correspond à l'offre, mais sans modifier les faits. N'ajoute pas une compétence de l'offre si elle n'est pas dans les extraits.
5. Neutralité : n'infère ni genre, âge, nationalité, situation familiale ni état de santé ; n'utilise pas de formulations qui avantagent ou pénalisent un profil.
6. Rédige en français, style professionnel concis (réalisations : une phrase, verbe d'action).
7. Le résumé (3 phrases max) ne reprend que des faits des extraits et liste ses `resume_sources`.
Réponds uniquement par un objet JSON conforme au schéma."""


def analyze_offer(offer_text: str) -> JobOffer:
    return llm.ask_json(OFFER_SYSTEM, f"Schéma : {OFFER_SCHEMA}\n\nOFFRE :\n{offer_text[:6000]}", JobOffer)


def _format_context(retrieved: dict[str, list[dict]]) -> tuple[str, dict[str, str]]:
    seen: dict[str, str] = {}
    parts: list[str] = []
    for section, items in retrieved.items():
        parts.append(f"=== SECTION : {section} ===")
        for it in items:
            seen[it["id"]] = it["text"]
            meta = it["meta"]
            parts.append(f"[{it['id']}] (type={meta.get('type')}, source={meta.get('source')}, dates={meta.get('dates') or '-'})\n{it['text']}")
    return "\n\n".join(parts), seen


def generate_cv(session_id: str, offer_text: str, use_fact_checker: bool = True) -> GenerationResult:
    if indexing.count_chunks(session_id) == 0:
        raise ValueError("Aucun document indexé : importez d'abord vos documents.")

    offer = analyze_offer(offer_text) if offer_text.strip() else JobOffer()
    retrieved = retrieve_all(session_id, offer if offer_text.strip() else None)
    context, sources = _format_context(retrieved)

    schema = json.dumps(CV.model_json_schema(), ensure_ascii=False)
    user = (
        f"OFFRE CIBLÉE (analysée) :\n{offer.model_dump_json(indent=1)}\n\n"
        f"CONTEXTE (seules sources autorisées) :\n{context}\n\n"
        f"SCHÉMA JSON À REMPLIR :\n{schema}\n\n"
        "Génère le CV adapté à l'offre."
    )
    cv = llm.ask_json(CV_SYSTEM, user, CV)

    cv = clean_non_renseigne(cv)
    cv = drop_unknown_sources(cv, set(sources))
    cv = check_identity(cv, "\n".join(sources.values()))
    cv, report = fact_check(cv, sources, ask_fn=llm.ask if use_fact_checker else None)

    return GenerationResult(cv=cv, offer=offer, report=report, chunks_used=sources)
