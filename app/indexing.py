"""Embeddings multilingues + base vectorielle Chroma (une collection par session)."""
from __future__ import annotations

from functools import lru_cache

from app.chunking import Chunk
from app.config import settings


class Embedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self._e5 = "e5" in model_name.lower()

    def _enc(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._enc([f"passage: {t}" for t in texts] if self._e5 else texts)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._enc([f"query: {t}" for t in texts] if self._e5 else texts)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder(settings.embedding_model)


def _collection(session_id: str):
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.session_dir(session_id) / "chroma"))
    return client.get_or_create_collection("documents", metadata={"hnsw:space": "cosine"})


def index_chunks(session_id: str, chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    col = _collection(session_id)
    col.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=get_embedder().embed_passages([c.text for c in chunks]),
        metadatas=[c.metadata() for c in chunks],
    )
    return len(chunks)


def count_chunks(session_id: str) -> int:
    return _collection(session_id).count()


def list_chunks(session_id: str) -> list[dict]:
    res = _collection(session_id).get()
    return [
        {"id": i, "text": d, **m}
        for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
    ]


def get_chunks_by_ids(session_id: str, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    res = _collection(session_id).get(ids=list(set(ids)))
    return dict(zip(res["ids"], res["documents"]))


def query(session_id: str, queries: list[str], k: int, types: list[str] | None = None) -> list[dict]:
    col = _collection(session_id)
    total = col.count()
    if total == 0:
        return []
    kwargs: dict = {"n_results": min(k, total)}
    if types:
        kwargs["where"] = {"type": {"$in": types}}
    res = col.query(query_embeddings=get_embedder().embed_queries(queries), **kwargs)
    best: dict[str, dict] = {}
    for qi in range(len(queries)):
        for cid, doc, meta, dist in zip(
            res["ids"][qi], res["documents"][qi], res["metadatas"][qi], res["distances"][qi]
        ):
            if cid not in best or dist < best[cid]["distance"]:
                best[cid] = {"id": cid, "text": doc, "meta": meta, "distance": dist}
    return sorted(best.values(), key=lambda r: r["distance"])
