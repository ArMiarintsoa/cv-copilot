from pathlib import Path

from app.chunking import DATE_RANGE, chunk_document

SAMPLE = Path(__file__).parent.parent / "data" / "samples" / "cv_ancien.txt"


def _chunks():
    return chunk_document(SAMPLE.read_text(encoding="utf-8"), "doctest", "cv_ancien.txt")


def test_one_experience_one_chunk():
    exp = [c for c in _chunks() if c.type == "experience"]
    assert len(exp) == 2
    assert "Orange Madagascar" in exp[0].text and "Jirama" not in exp[0].text
    assert "Jirama" in exp[1].text


def test_formations_split_and_dates():
    forms = [c for c in _chunks() if c.type == "formation"]
    assert len(forms) == 2
    assert all(c.dates for c in forms)


def test_section_types_present():
    types = {c.type for c in _chunks()}
    assert {"identite", "resume", "experience", "formation", "competences", "langues", "projets", "certifications"} <= types


def test_chunk_ids_unique_and_prefixed():
    ids = [c.chunk_id for c in _chunks()]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("doctest_chunk") for i in ids)


def test_document_without_headings_is_autre():
    chunks = chunk_document("Madame, Monsieur,\n\nJe vous écris pour postuler.", "d1", "lettre.txt")
    assert chunks and all(c.type == "autre" for c in chunks)


def test_date_range_regex():
    for s in ["Janvier 2022 - Présent", "2019 - 2021", "06/2021 – 12/2021", "mars 2020 à juin 2021"]:
        assert DATE_RANGE.search(s), s
