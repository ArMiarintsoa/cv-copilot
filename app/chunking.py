"""Chunking sémantique : une expérience / formation / projet = un chunk, avec métadonnées."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import settings

SECTION_PATTERNS: dict[str, str] = {
    "experience": r"exp[ée]riences?(\s+professionnelles?)?|parcours professionnel|work experience|professional experience|employment(\s+history)?",
    "formation": r"formations?|[ée]ducation|dipl[oô]mes?|cursus|parcours acad[ée]mique",
    "competences": r"comp[ée]tences?(\s+techniques?)?|skills|technical skills|technologies|outils",
    "langues": r"langues?|languages?",
    "projets": r"projets?|projects?|r[ée]alisations",
    "certifications": r"certifications?|certificats?|licenses?",
    "resume": r"profil|r[ée]sum[ée]|summary|about(\s+me)?|[àa] propos|objectif",
    "centres_interet": r"centres? d.int[ée]r[êe]ts?|loisirs|hobbies|interests",
}
_HEADING_RES = {k: re.compile(rf"^(?:{v})$", re.I) for k, v in SECTION_PATTERNS.items()}

_MONTH = r"(?:janv?\.?|f[ée]vr?\.?|mars|avr\.?|mai|juin|juil\.?|ao[uû]t|sept?\.?|oct\.?|nov\.?|d[ée]c\.?|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-zéèêû]*"
_END = r"(?:\d{1,2}/\d{4}|\d{4}|pr[ée]sent|aujourd.hui|actuel|present|now|en cours)"
_START = rf"(?:{_MONTH}\.?\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
DATE_RANGE = re.compile(rf"{_START}\s*(?:-|–|—|à|to)\s*(?:{_MONTH}\.?\s+)?{_END}", re.I)

ENTRY_SECTIONS = {"experience", "formation", "projets", "certifications"}
SINGLE_CHUNK_SECTIONS = {"identite", "resume", "competences", "langues", "centres_interet"}


@dataclass
class Chunk:
    chunk_id: str
    text: str
    type: str
    source: str
    dates: str = ""
    doc_id: str = ""
    meta: dict = field(default_factory=dict)

    def metadata(self) -> dict:
        return {"type": self.type, "source": self.source, "dates": self.dates, "doc_id": self.doc_id}


def _heading_type(line: str) -> str | None:
    s = re.sub(r"[:\-–—_*#=•\s]+$", "", line.strip())
    s = re.sub(r"^[#*•\-–—\s\d.]+", "", s)
    if not s or len(s) > 40:
        return None
    for name, rx in _HEADING_RES.items():
        if rx.match(s):
            return name
    return None


def split_sections(text: str) -> list[tuple[str, list[str]]]:
    """Découpe le texte en sections (type, lignes). Avant tout titre : 'identite'."""
    sections: list[tuple[str, list[str]]] = []
    current_type = "identite"
    current: list[str] = []
    seen_heading = False
    for line in text.split("\n"):
        h = _heading_type(line)
        if h:
            if current:
                sections.append((current_type, current))
            current_type, current, seen_heading = h, [], True
        else:
            current.append(line)
    if current:
        sections.append((current_type, current))
    if not seen_heading:  # document sans titres (lettre, fiche de poste…)
        return [("autre", text.split("\n"))]
    return sections


def _split_entries(lines: list[str]) -> list[str]:
    """Une entrée commence à une ligne de dates si le bloc courant en contient déjà une."""
    blocks: list[list[str]] = []
    cur: list[str] = []
    cur_has_date = False
    for line in lines:
        has_date = bool(DATE_RANGE.search(line))
        if not line.strip():
            if cur and cur_has_date and len(cur) >= 2:
                blocks.append(cur)
                cur, cur_has_date = [], False
            continue
        if has_date and cur_has_date:
            blocks.append(cur)
            cur, cur_has_date = [], False
        cur.append(line)
        cur_has_date = cur_has_date or has_date
    if cur:
        blocks.append(cur)
    return ["\n".join(b).strip() for b in blocks if "\n".join(b).strip()]


def _split_by_words(text: str, max_words: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur, n = [], [], 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > max_words:
            out.append("\n\n".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
    if cur:
        out.append("\n\n".join(cur))
    final = []
    for block in out:  # bloc unique trop long : découpe dure par mots
        words = block.split()
        if len(words) <= max_words * 2:
            final.append(block)
        else:
            for i in range(0, len(words), max_words):
                final.append(" ".join(words[i : i + max_words]))
    return final


def chunk_document(text: str, doc_id: str, source: str, start_index: int = 0) -> list[Chunk]:
    chunks: list[Chunk] = []
    n = start_index
    for sec_type, lines in split_sections(text):
        body = "\n".join(lines).strip()
        if not body:
            continue
        if sec_type in ENTRY_SECTIONS:
            pieces = _split_entries(lines)
        elif sec_type in SINGLE_CHUNK_SECTIONS:
            pieces = _split_by_words(body, settings.max_chunk_words)
        else:
            pieces = _split_by_words(body, settings.max_chunk_words)
        for piece in pieces:
            m = DATE_RANGE.search(piece)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}_chunk{n}",
                    text=piece,
                    type=sec_type,
                    source=source,
                    dates=m.group(0) if m else "",
                    doc_id=doc_id,
                )
            )
            n += 1
    return chunks
