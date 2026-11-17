"""Rendu du CV : Jinja2 + WeasyPrint (PDF) et python-docx (DOCX)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas import CV

TEMPLATES = Path(__file__).parent / "templates"


def render_html(cv: CV) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    return env.get_template("cv.html.j2").render(cv=cv)


def render_pdf(cv: CV) -> bytes:
    from weasyprint import HTML

    return HTML(string=render_html(cv)).write_pdf()


def render_docx(cv: CV, path: Path) -> Path:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    i = cv.identite

    if i.nom:
        d.add_heading(i.nom, 0)
    if i.titre:
        d.add_paragraph(i.titre).runs[0].bold = True
    contact = " · ".join(x for x in [i.email, i.telephone, i.localisation, *i.liens] if x)
    if contact:
        d.add_paragraph(contact)

    if cv.resume:
        d.add_heading("Profil", 1)
        d.add_paragraph(cv.resume)

    if cv.experiences:
        d.add_heading("Expérience professionnelle", 1)
        for e in cv.experiences:
            p = d.add_paragraph()
            r = p.add_run(f"{e.poste}" + (f" — {e.entreprise}" if e.entreprise else ""))
            r.bold = True
            if e.dates:
                p.add_run(f"   {e.dates}")
            for real in e.realisations:
                d.add_paragraph(real.texte, style="List Bullet")

    if cv.formations:
        d.add_heading("Formation", 1)
        for f in cv.formations:
            p = d.add_paragraph()
            p.add_run(f.diplome + (f" — {f.etablissement}" if f.etablissement else "")).bold = True
            if f.dates:
                p.add_run(f"   {f.dates}")

    if cv.projets:
        d.add_heading("Projets", 1)
        for pr in cv.projets:
            p = d.add_paragraph()
            p.add_run(pr.nom).bold = True
            if pr.description:
                d.add_paragraph(pr.description)
            if pr.technologies:
                d.add_paragraph("Technologies : " + ", ".join(pr.technologies))

    if cv.competences.techniques:
        d.add_heading("Compétences", 1)
        d.add_paragraph(", ".join(c.texte for c in cv.competences.techniques))
    if cv.competences.langues:
        d.add_heading("Langues", 1)
        d.add_paragraph(", ".join(c.texte for c in cv.competences.langues))
    if cv.certifications:
        d.add_heading("Certifications", 1)
        for c in cv.certifications:
            d.add_paragraph(c.texte, style="List Bullet")

    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))
    return path
