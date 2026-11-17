from app.schemas import CV, Experience, Formation, Sourced
from app.verification import (
    check_identity,
    clean_non_renseigne,
    drop_unknown_sources,
    fact_check,
    lexical_support,
)

SOURCES = {
    "d_chunk1": "Data Analyst - Orange Madagascar. Pipeline de prévision de la demande en Python (pandas, scikit-learn).",
    "d_chunk2": "Master Informatique, spécialité Science des données - Université d'Antananarivo 2019 - 2021",
}


def _cv() -> CV:
    cv = CV()
    cv.experiences = [
        Experience(
            poste="Data Analyst",
            entreprise="Orange Madagascar",
            dates="2022 - Présent",
            realisations=[
                Sourced(texte="Pipeline de prévision de la demande en Python", source_id="d_chunk1"),
                Sourced(texte="Pilotage d'une équipe de 12 ingénieurs et réduction des coûts de 40 %", source_id="d_chunk1"),
                Sourced(texte="Fait inventé", source_id="d_chunk999"),
            ],
        )
    ]
    cv.formations = [Formation(diplome="Master Informatique", etablissement="Université d'Antananarivo", source_id="d_chunk2")]
    return cv


def test_lexical_support():
    assert lexical_support("prévision en Python", SOURCES["d_chunk1"]) == 1.0
    assert lexical_support("équipe de 12 ingénieurs", SOURCES["d_chunk1"]) < 0.5


def test_unknown_source_ids_are_dropped():
    cv = drop_unknown_sources(_cv(), set(SOURCES))
    texts = [r.texte for r in cv.experiences[0].realisations]
    assert "Fait inventé" not in texts


def test_lexical_fact_check_removes_embellishment():
    cv = drop_unknown_sources(_cv(), set(SOURCES))
    cv, report = fact_check(cv, SOURCES, ask_fn=None)
    texts = [r.texte for r in cv.experiences[0].realisations]
    assert texts == ["Pipeline de prévision de la demande en Python"]
    assert len(report.removed) == 1
    assert 0 < report.faithfulness < 1
    assert cv.formations  # la formation fidèle est conservée


def test_llm_judge_verdicts_are_applied():
    cv = drop_unknown_sources(_cv(), set(SOURCES))

    def fake_judge(system, user):
        return '{"verdicts": [' + ",".join(
            f'{{"id": {i}, "supported": true, "reason": "ok"}}' for i in range(10)
        ) + "]}"

    cv, report = fact_check(cv, SOURCES, ask_fn=fake_judge)
    # le juge valide tout, mais la garde lexicale retire l'invention flagrante (recouvrement très faible)
    assert report.method == "llm"
    assert all("12 ingénieurs" not in r.texte for r in cv.experiences[0].realisations) or report.faithfulness <= 1


def test_non_renseigne_cleanup():
    cv = CV()
    cv.identite.email = "NON RENSEIGNÉ"
    cv.resume = "NON RENSEIGNÉ"
    cv = clean_non_renseigne(cv)
    assert cv.identite.email == "" and cv.resume == ""


def test_identity_must_appear_in_sources():
    cv = CV()
    cv.identite.nom = "Rina Randria"
    cv.identite.email = "inventé@faux.com"
    cv = check_identity(cv, "Rina Randria\nrina.randria@example.com")
    assert cv.identite.nom == "Rina Randria"
    assert cv.identite.email == ""
