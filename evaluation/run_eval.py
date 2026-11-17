"""Évaluation complète d'un jeu de test annoté.

Usage :
    python -m evaluation.run_eval --dataset evaluation/dataset.example.json --k 5

Format du dataset (JSON) :
{
  "documents": ["data/samples/cv_ancien.txt"],
  "offer": "data/samples/offre_exemple.txt",
  "retrieval_queries": [{"query": "...", "relevant_texts": ["extrait attendu dans le chunk"]}],
  "expected_facts": ["Python", "Master"]
}
Les chunks pertinents sont désignés par un extrait de texte (robuste aux ids de chunks, qui dépendent du hash).
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from app import indexing
from app.chunking import chunk_document
from app.generation import generate_cv
from app.ingestion import extract_text, make_doc_id
from evaluation.metrics import coverage, cosine, mean, recall_at_k, reciprocal_rank


def run(dataset_path: Path, k: int) -> dict:
    ds = json.loads(dataset_path.read_text(encoding="utf-8"))
    sid = f"eval-{uuid.uuid4().hex[:8]}"

    for doc in ds["documents"]:
        p = Path(doc)
        text = extract_text(p)
        indexing.index_chunks(sid, chunk_document(text, make_doc_id(p.name, text), p.name))
    all_chunks = indexing.list_chunks(sid)

    # --- Qualité du retrieval : Recall@k, MRR
    recalls, rrs = [], []
    for q in ds.get("retrieval_queries", []):
        relevant = {c["id"] for c in all_chunks if any(t.lower() in c["text"].lower() for t in q["relevant_texts"])}
        got = [r["id"] for r in indexing.query(sid, [q["query"]], k)]
        recalls.append(recall_at_k(got, relevant, k))
        rrs.append(reciprocal_rank(got, relevant))

    # --- Génération : fidélité, couverture, pertinence vs offre
    offer_text = Path(ds["offer"]).read_text(encoding="utf-8") if ds.get("offer") else ""
    generic = generate_cv(sid, "")
    adapted = generate_cv(sid, offer_text)
    emb = indexing.get_embedder()

    def cv_text(r):
        return r.cv.model_dump_json()

    sims = {}
    if offer_text:
        v = emb.embed_passages([offer_text, cv_text(generic), cv_text(adapted)])
        sims = {"offre_vs_cv_generique": cosine(v[0], v[1]), "offre_vs_cv_adapte": cosine(v[0], v[2])}

    return {
        "retrieval": {f"recall@{k}": mean(recalls), "mrr": mean(rrs), "n_queries": len(recalls)},
        "fidelite": {"generique": generic.report.faithfulness, "adapte": adapted.report.faithfulness,
                     "affirmations_retirees_adapte": len(adapted.report.removed)},
        "couverture": coverage(ds.get("expected_facts", []), cv_text(adapted)),
        "pertinence_offre": sims,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()
    results = run(args.dataset, args.k)
    out = Path("evaluation/results")
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
