from app.rendering import render_html
from app.schemas import CV, Experience, Sourced


def test_html_contains_facts_and_escapes():
    cv = CV()
    cv.identite.nom = "Rina <b>Randria</b>"
    cv.experiences = [Experience(poste="Data Analyst", entreprise="Orange", dates="2022 - Présent",
                                 realisations=[Sourced(texte="Prévision en Python", source_id="x")])]
    html = render_html(cv)
    assert "Prévision en Python" in html and "Data Analyst" in html
    assert "<b>Randria</b>" not in html  # échappement HTML


def test_cv_schema_roundtrip():
    cv = CV.model_validate_json(CV().model_dump_json())
    assert cv.experiences == []
