"""Interface Streamlit : import -> offre -> génération -> vérification -> export."""
import json
import os
import uuid

import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="CV Copilot", page_icon="📄", layout="wide")
st.title("📄 CV Copilot")
st.caption("Un CV adapté à l'offre, construit uniquement à partir de vos documents. Aucune information inventée.")

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:12]
sid = st.session_state.session_id

with st.sidebar:
    st.subheader("1. Vos documents")
    files = st.file_uploader("PDF, DOCX ou TXT", type=["pdf", "docx", "txt"], accept_multiple_files=True)
    if st.button("Indexer les documents", disabled=not files):
        with st.spinner("Extraction et indexation…"):
            r = requests.post(
                f"{API}/documents",
                data={"session_id": sid},
                files=[("files", (f.name, f.getvalue())) for f in files],
                timeout=600,
            )
        if r.ok:
            data = r.json()
            for d in data["documents"]:
                (st.error if "error" in d else st.success)(
                    f"{d['file']} : {d.get('error') or str(d['chunks']) + ' passages'}"
                )
            st.session_state.total_chunks = data["total_chunks"]
        else:
            st.error(r.text)
    if st.session_state.get("total_chunks"):
        st.info(f"{st.session_state.total_chunks} passages indexés")
    fact = st.toggle("Vérificateur de faits (2e passage LLM)", value=True)
    st.caption(f"Session : {sid}")

col_in, col_out = st.columns([1, 1.3])

with col_in:
    st.subheader("2. L'offre d'emploi")
    offer = st.text_area("Collez l'offre (laisser vide = CV générique)", height=320)
    go = st.button("Générer mon CV", type="primary", disabled=not st.session_state.get("total_chunks"))

if go:
    with st.spinner("Recherche des passages, génération puis vérification…"):
        r = requests.post(
            f"{API}/generate",
            json={"session_id": sid, "offer_text": offer, "fact_checker": fact},
            timeout=600,
        )
    if r.ok:
        st.session_state.result = r.json()
    else:
        try:
            err_msg = r.json().get("detail", r.text)
        except Exception:
            err_msg = r.text or f"Erreur HTTP {r.status_code}"
        st.error(err_msg)

with col_out:
    st.subheader("3. Résultat")
    res = st.session_state.get("result")
    if not res:
        st.write("Le CV apparaîtra ici.")
    else:
        rep = res["report"]
        st.metric("Fidélité aux sources", f"{rep['faithfulness']:.0%}",
                  help=f"{rep['supported_claims']}/{rep['total_claims']} affirmations soutenues ({rep['method']})")
        if rep["removed"]:
            with st.expander(f"⚠️ {len(rep['removed'])} affirmation(s) retirée(s) car non soutenues"):
                for v in rep["removed"]:
                    st.write(f"- {v['claim']}  \n  _{v['reason']}_")

        tab_cv, tab_json, tab_src = st.tabs(["CV", "JSON (éditable)", "Sources"])
        with tab_json:
            edited = st.text_area("JSON du CV", json.dumps(res["cv"], ensure_ascii=False, indent=2), height=420)
            try:
                cv = json.loads(edited)
            except json.JSONDecodeError as e:
                st.error(f"JSON invalide : {e}")
                cv = res["cv"]
        with tab_cv:
            i = cv["identite"]
            st.markdown(f"### {i['nom'] or '—'}\n**{i['titre']}**  \n{' · '.join(x for x in [i['email'], i['telephone'], i['localisation']] if x)}")
            if cv["resume"]:
                st.write(cv["resume"])
            for e in cv["experiences"]:
                st.markdown(f"**{e['poste']} — {e['entreprise']}** · _{e['dates']}_")
                for rr in e["realisations"]:
                    st.markdown(f"- {rr['texte']} `{rr['source_id']}`")
            for f in cv["formations"]:
                st.markdown(f"🎓 **{f['diplome']}** — {f['etablissement']} · _{f['dates']}_")
            if cv["competences"]["techniques"]:
                st.markdown("**Compétences :** " + ", ".join(c["texte"] for c in cv["competences"]["techniques"]))
            if cv["competences"]["langues"]:
                st.markdown("**Langues :** " + ", ".join(c["texte"] for c in cv["competences"]["langues"]))
        with tab_src:
            for cid, txt in res["chunks_used"].items():
                with st.expander(cid):
                    st.text(txt)

        c1, c2 = st.columns(2)
        for fmt, col in (("pdf", c1), ("docx", c2)):
            rr = requests.post(f"{API}/render", json={"cv": cv, "format": fmt}, timeout=120)
            if rr.ok:
                col.download_button(f"Télécharger {fmt.upper()}", rr.content, file_name=f"cv.{fmt}")
            else:
                col.warning(f"{fmt.upper()} indisponible : {rr.text[:120]}")
