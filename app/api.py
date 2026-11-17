"""API FastAPI : import de documents, génération du CV, export PDF/DOCX."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app import indexing
from app.chunking import chunk_document
from app.config import settings
from app.generation import generate_cv
from app.ingestion import SUPPORTED, extract_text, make_doc_id
from app.schemas import CV, GenerationResult

app = FastAPI(title="CV Copilot", version="0.1.0")


class GenerateRequest(BaseModel):
    session_id: str
    offer_text: str = ""
    fact_checker: bool = True


class RenderRequest(BaseModel):
    cv: CV
    format: str = "pdf"  # pdf | docx


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider, "embeddings": settings.embedding_model}


@app.post("/documents")
async def upload_documents(session_id: str = Form(...), files: list[UploadFile] = File(...)):
    uploads = settings.session_dir(session_id) / "uploads"
    uploads.mkdir(exist_ok=True)
    report = []
    for f in files:
        name = Path(f.filename or "document").name
        ext = Path(name).suffix.lower()
        if ext not in SUPPORTED:
            report.append({"file": name, "error": f"format non supporté ({ext})"})
            continue
        dest = uploads / name
        dest.write_bytes(await f.read())
        try:
            text = extract_text(dest)
            if len(text) < 30:
                report.append({"file": name, "error": "aucun texte extractible (PDF scanné ?)"})
                continue
            doc_id = make_doc_id(name, text)
            n = indexing.index_chunks(session_id, chunk_document(text, doc_id, name))
            report.append({"file": name, "doc_id": doc_id, "chunks": n})
        except Exception as e:  # noqa: BLE001
            report.append({"file": name, "error": str(e)})
    return {"documents": report, "total_chunks": indexing.count_chunks(session_id)}


@app.get("/documents/{session_id}/chunks")
def chunks(session_id: str):
    return indexing.list_chunks(session_id)


@app.post("/generate", response_model=GenerationResult)
def generate(req: GenerateRequest):
    try:
        return generate_cv(req.session_id, req.offer_text, req.fact_checker)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/render")
def render(req: RenderRequest):
    from app import rendering

    if req.format == "pdf":
        try:
            return Response(rendering.render_pdf(req.cv), media_type="application/pdf",
                            headers={"Content-Disposition": 'attachment; filename="cv.pdf"'})
        except OSError as e:  # bibliothèques système WeasyPrint manquantes
            raise HTTPException(500, f"Rendu PDF indisponible : {e}") from e
    if req.format == "docx":
        tmp = Path(tempfile.mkdtemp()) / "cv.docx"
        rendering.render_docx(req.cv, tmp)
        return FileResponse(tmp, filename="cv.docx",
                            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    raise HTTPException(400, "format attendu : pdf ou docx")
