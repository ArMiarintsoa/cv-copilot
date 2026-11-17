"""Vérification anti-hallucination : validation des source_id + fact-checker (LLM-as-judge) + repli lexical."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from app.schemas import CV, NON_RENSEIGNE, ClaimVerdict, VerificationReport

_STOP = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en", "au", "aux", "pour", "par", "sur", "avec",
    "dans", "que", "qui", "à", "a", "d", "l", "the", "of", "and", "to", "in", "for", "with", "ce", "se", "son", "sa", "ses",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\wÀ-ÿ+#.]+", text.lower()) if t not in _STOP and len(t) > 1}


def lexical_support(claim: str, source: str) -> float:
    """Part des mots significatifs de l'affirmation présents dans la source (0..1)."""
    ct = _tokens(claim)
    if not ct:
        return 1.0
    return len(ct & _tokens(source)) / len(ct)


@dataclass
class Claim:
    text: str
    sources: list[str]
    container: list | None  # liste d'où retirer l'élément (None = champ simple)
    item: object
    label: str


def clean_non_renseigne(cv: CV) -> CV:
    """Retire les champs que le LLM a marqués NON RENSEIGNÉ."""

    def bad(s: str) -> bool:
        return NON_RENSEIGNE.lower() in (s or "").lower()

    ident = cv.identite
    for f in ("nom", "email", "telephone", "localisation", "titre"):
        if bad(getattr(ident, f)):
            setattr(ident, f, "")
    ident.liens = [x for x in ident.liens if not bad(x)]
    if bad(cv.resume):
        cv.resume = ""
    for e in cv.experiences:
        for f in ("poste", "entreprise", "dates"):
            if bad(getattr(e, f)):
                setattr(e, f, "")
        e.realisations = [r for r in e.realisations if not bad(r.texte)]
    for f in cv.formations:
        for k in ("diplome", "etablissement", "dates"):
            if bad(getattr(f, k)):
                setattr(f, k, "")
    cv.formations = [f for f in cv.formations if f.diplome or f.etablissement]
    cv.experiences = [e for e in cv.experiences if e.poste or e.entreprise]
    cv.projets = [p for p in cv.projets if p.nom and not bad(p.nom)]
    cv.certifications = [c for c in cv.certifications if not bad(c.texte)]
    cv.competences.techniques = [c for c in cv.competences.techniques if not bad(c.texte)]
    cv.competences.langues = [c for c in cv.competences.langues if not bad(c.texte)]
    return cv


def drop_unknown_sources(cv: CV, valid_ids: set[str]) -> CV:
    """Un fait dont le source_id n'existe pas dans les chunks retrouvés est une hallucination : on le retire."""
    for e in cv.experiences:
        e.realisations = [r for r in e.realisations if r.source_id in valid_ids]
    cv.experiences = [e for e in cv.experiences if e.realisations or (e.poste and e.entreprise)]
    cv.formations = [f for f in cv.formations if f.source_id in valid_ids]
    cv.projets = [p for p in cv.projets if p.source_id in valid_ids]
    cv.certifications = [c for c in cv.certifications if c.source_id in valid_ids]
    cv.competences.techniques = [c for c in cv.competences.techniques if c.source_id in valid_ids]
    cv.competences.langues = [c for c in cv.competences.langues if c.source_id in valid_ids]
    cv.resume_sources = [s for s in cv.resume_sources if s in valid_ids]
    cv.identite.sources = [s for s in cv.identite.sources if s in valid_ids]
    if cv.resume and not cv.resume_sources:
        cv.resume = ""
    return cv


def collect_claims(cv: CV) -> list[Claim]:
    claims: list[Claim] = []
    if cv.resume:
        claims.append(Claim(cv.resume, cv.resume_sources, None, "resume", "résumé"))
    if cv.identite.titre:
        claims.append(Claim(cv.identite.titre, cv.identite.sources, None, "titre", "titre"))
    for e in cv.experiences:
        for r in e.realisations:
            claims.append(Claim(f"{e.poste} chez {e.entreprise} : {r.texte}", [r.source_id], e.realisations, r, "réalisation"))
    for f in cv.formations:
        claims.append(Claim(f"{f.diplome} - {f.etablissement} {f.dates}", [f.source_id], cv.formations, f, "formation"))
    for p in cv.projets:
        claims.append(Claim(f"{p.nom} : {p.description} {' '.join(p.technologies)}", [p.source_id], cv.projets, p, "projet"))
    for c in cv.certifications:
        claims.append(Claim(c.texte, [c.source_id], cv.certifications, c, "certification"))
    for c in cv.competences.techniques:
        claims.append(Claim(c.texte, [c.source_id], cv.competences.techniques, c, "compétence"))
    for c in cv.competences.langues:
        claims.append(Claim(c.texte, [c.source_id], cv.competences.langues, c, "langue"))
    return claims


JUDGE_SYSTEM = (
    "Tu es un vérificateur de faits strict. Pour chaque affirmation d'un CV, tu dis si elle est ENTIÈREMENT "
    "soutenue par les extraits sources cités. Une affirmation est non soutenue si elle contient un chiffre, une "
    "durée, un outil, un diplôme, un niveau ou une responsabilité absent des sources, ou si elle l'exagère. "
    "Une simple reformulation fidèle est soutenue. Réponds uniquement en JSON."
)


def _judge_batch(batch: list[tuple[int, Claim]], sources: dict[str, str], ask_fn: Callable[[str, str], str]) -> dict[int, tuple[bool, str]]:
    payload = [
        {
            "id": i,
            "affirmation": c.text,
            "sources": {sid: sources.get(sid, "") for sid in c.sources},
        }
        for i, c in batch
    ]
    user = (
        "Vérifie chaque affirmation.\n"
        'Format : {"verdicts":[{"id":0,"supported":true,"reason":"..."}]}\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )
    raw = ask_fn(JUDGE_SYSTEM, user)
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start : end + 1])
    return {int(v["id"]): (bool(v["supported"]), str(v.get("reason", ""))) for v in data["verdicts"]}


def fact_check(
    cv: CV,
    sources: dict[str, str],
    ask_fn: Callable[[str, str], str] | None = None,
    lexical_threshold: float = 0.6,
    batch_size: int = 15,
) -> tuple[CV, VerificationReport]:
    """Retire les affirmations non soutenues. Sans LLM (ask_fn=None) : contrôle lexical uniquement."""
    claims = collect_claims(cv)
    verdicts: dict[int, tuple[bool, str]] = {}
    method = "llm" if ask_fn else "lexical"

    indexed = list(enumerate(claims))
    if ask_fn:
        for i in range(0, len(indexed), batch_size):
            batch = indexed[i : i + batch_size]
            try:
                verdicts.update(_judge_batch(batch, sources, ask_fn))
            except Exception:  # juge indisponible/invalide : repli lexical pour ce lot
                method = "llm+lexical"
    for i, c in indexed:
        if i not in verdicts:
            src = " ".join(sources.get(s, "") for s in c.sources)
            score = lexical_support(c.text, src)
            verdicts[i] = (score >= lexical_threshold, f"recouvrement lexical {score:.0%}")
        elif verdicts[i][0] and ask_fn:
            # double garde : même validé par le juge, un recouvrement très faible est suspect
            src = " ".join(sources.get(s, "") for s in c.sources)
            if lexical_support(c.text, src) < 0.25:
                verdicts[i] = (False, "recouvrement lexical très faible malgré le verdict du juge")

    removed: list[ClaimVerdict] = []
    supported = 0
    for i, c in indexed:
        ok, reason = verdicts[i]
        if ok:
            supported += 1
            continue
        removed.append(ClaimVerdict(claim=c.text, source_ids=c.sources, supported=False, reason=reason))
        if c.container is not None:
            if c.item in c.container:
                c.container.remove(c.item)
        elif c.item == "resume":
            cv.resume = ""
        elif c.item == "titre":
            cv.identite.titre = ""

    cv.experiences = [e for e in cv.experiences if e.realisations]
    total = len(claims)
    report = VerificationReport(
        total_claims=total,
        supported_claims=supported,
        faithfulness=round(supported / total, 3) if total else 1.0,
        removed=removed,
        method=method,
    )
    return cv, report


def check_identity(cv: CV, all_text: str) -> CV:
    """Nom, e-mail, téléphone : doivent apparaître tels quels dans les documents."""
    low = all_text.lower()
    compact = re.sub(r"[\s.\-()]", "", all_text)
    ident = cv.identite
    if ident.nom and not all(p in low for p in ident.nom.lower().split()):
        ident.nom = ""
    if ident.email and ident.email.lower() not in low:
        ident.email = ""
    if ident.telephone and re.sub(r"[\s.\-()]", "", ident.telephone) not in compact:
        ident.telephone = ""
    ident.liens = [l for l in ident.liens if l.lower().strip("/") in low or l.lower() in low]
    return cv
