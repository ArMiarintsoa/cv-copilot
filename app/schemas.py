"""Schémas Pydantic : CV structuré, offre d'emploi, rapport de vérification."""
from __future__ import annotations

from pydantic import BaseModel, Field

NON_RENSEIGNE = "NON RENSEIGNÉ"


class Sourced(BaseModel):
    """Un fait du CV rattaché au chunk d'où il provient."""

    texte: str = ""
    source_id: str = ""


class Identite(BaseModel):
    nom: str = ""
    email: str = ""
    telephone: str = ""
    localisation: str = ""
    liens: list[str] = Field(default_factory=list)
    titre: str = ""
    sources: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    poste: str = ""
    entreprise: str = ""
    dates: str = ""
    realisations: list[Sourced] = Field(default_factory=list)


class Formation(BaseModel):
    diplome: str = ""
    etablissement: str = ""
    dates: str = ""
    source_id: str = ""


class Projet(BaseModel):
    nom: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    source_id: str = ""


class Competences(BaseModel):
    techniques: list[Sourced] = Field(default_factory=list)
    langues: list[Sourced] = Field(default_factory=list)


class CV(BaseModel):
    identite: Identite = Field(default_factory=Identite)
    resume: str = ""
    resume_sources: list[str] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    formations: list[Formation] = Field(default_factory=list)
    projets: list[Projet] = Field(default_factory=list)
    certifications: list[Sourced] = Field(default_factory=list)
    competences: Competences = Field(default_factory=Competences)


class JobOffer(BaseModel):
    titre: str = ""
    entreprise: str = ""
    competences_requises: list[str] = Field(default_factory=list)
    mots_cles: list[str] = Field(default_factory=list)
    responsabilites: list[str] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    claim: str
    source_ids: list[str]
    supported: bool
    reason: str = ""


class VerificationReport(BaseModel):
    total_claims: int = 0
    supported_claims: int = 0
    faithfulness: float = 1.0
    removed: list[ClaimVerdict] = Field(default_factory=list)
    method: str = "llm"


class GenerationResult(BaseModel):
    cv: CV
    offer: JobOffer
    report: VerificationReport
    chunks_used: dict[str, str] = Field(default_factory=dict)
