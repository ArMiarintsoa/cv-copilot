"""Ingestion : extraction du texte (PDF, DOCX, TXT) et nettoyage."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".txt"}


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        raw = _read_pdf(path)
    elif ext == ".docx":
        raw = _read_docx(path)
    elif ext == ".txt":
        raw = _read_txt(path)
    else:
        raise ValueError(f"Format non supporté : {ext} (attendu : {', '.join(sorted(SUPPORTED))})")
    return clean_text(raw)


def _read_pdf(path: Path) -> str:
    import pymupdf

    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text("text") for page in doc)


def _read_docx(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_txt(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"-\n(?=[a-zàâçéèêëîïôûùüÿ])", "", text)  # césures
    text = re.sub(r"^\s*(page\s*)?\d+\s*(/|sur|of)\s*\d+\s*$", "", text, flags=re.I | re.M)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_doc_id(filename: str, content: str) -> str:
    h = hashlib.sha1((filename + content).encode("utf-8", errors="ignore")).hexdigest()[:6]
    return f"doc{h}"
