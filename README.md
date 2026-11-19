# 📄 CV Copilot

Assistant IA qui **remplit et adapte votre CV** à partir de vos propres documents (anciens CV, lettres, certificats, profil LinkedIn exporté, rapports de projet), **sans inventer d'informations**.

## Pourquoi un RAG ?

Un LLM seul peut inventer un diplôme ou une compétence. Ici, chaque ligne du CV est générée à partir de passages réellement retrouvés dans vos documents, et rattachée à un `source_id` vérifiable.

## Architecture

```
Documents → Parsing → Chunking → Embeddings → Chroma
                                                 ↓
Offre d'emploi → Analyse + requêtes → Retrieval (top-k + rerank)
                                                 ↓
                     LLM (prompt strict + schéma JSON Pydantic) → CV structuré
                                                 ↓
        Validation des source_id → Fact-checker → Template → PDF / DOCX
```

| Étape | Module | Détail |
|---|---|---|
| Ingestion | `app/ingestion.py` | PyMuPDF (PDF), python-docx, TXT multi-encodage ; nettoyage |
| Chunking | `app/chunking.py` | Une expérience/formation/projet = un chunk ; métadonnées `type`, `dates`, `source` |
| Indexation | `app/indexing.py` | bge-m3 / multilingual-e5 → Chroma (une collection par session) |
| Retrieval | `app/retrieval.py` | Requête ciblée par section + mots-clés de l'offre + reranker optionnel |
| Génération | `app/generation.py` | LLM remplit le schéma `CV` ; « NON RENSEIGNÉ » si absent |
| Vérification | `app/verification.py` | (1) `source_id` inexistant → supprimé (2) juge LLM par affirmation (3) garde lexicale (4) identité contrôlée mot à mot |
| Rendu | `app/rendering.py` | Jinja2 + WeasyPrint (PDF), python-docx (DOCX) |
| API / UI | `app/api.py`, `streamlit_app.py` | FastAPI + Streamlit |

## Installation

```bash
python -m venv .venv
.venv/Scripts/activate
python -m pip install -r requirements.txt
cp .env.example .env       
```

- Pour tester vite, utilisez `EMBEDDING_MODEL=intfloat/multilingual-e5-small` (léger) ; `BAAI/bge-m3` donne la meilleure qualité (~2 Go).
- WeasyPrint demande des bibliothèques système (Pango) : voir la doc WeasyPrint. Sans elles, l'export DOCX reste disponible.
- Ollama : `ollama pull mistral` puis `LLM_PROVIDER=ollama`.

## Lancer

```bash
uvicorn app.api:app --reload          # terminal 1 : API sur :8000
streamlit run streamlit_app.py        # terminal 2 : interface sur :8501
```

Documents d'exemple : `data/samples/` (CV fictif + offre).

## Tests

```bash
pytest -q       # chunking, vérification anti-hallucination, métriques, rendu (sans LLM ni modèle d'embeddings)
```

## Évaluation (projet académique)

```bash
python -m evaluation.run_eval --dataset evaluation/dataset.example.json --k 5
```

| Critère | Mesure | Où |
|---|---|---|
| Fidélité | % d'affirmations soutenues (juge LLM + garde lexicale) | `VerificationReport.faithfulness` ; compléter par une vérification manuelle d'un échantillon |
| Couverture | faits annotés retrouvés dans le CV | `evaluation/metrics.py::coverage` |
| Pertinence vs offre | similarité cosinus offre / CV, **avant (générique) vs après (adapté)** | `run_eval.py` |
| Retrieval | Recall@k, MRR sur requêtes annotées | `run_eval.py` |
| Test utilisateur | 5–10 personnes, qualité + gain de temps | questionnaire à prévoir |

RAGAS / TruLens peuvent s'ajouter par-dessus : les `chunks_used` et le CV sont déjà exposés par `/generate`.
