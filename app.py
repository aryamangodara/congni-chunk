import textwrap
from pathlib import Path

import streamlit as st

from cogni_chunk_engine import TechnicalDocAnalyst


st.set_page_config(
    page_title="Cogni Chunk 📚",
    page_icon="CK",
    layout="wide",
)


DOCUMENTS = {
    "Technical Architecture Dossier": Path("technical_doc.md"),
    "Geometry Notes PDF": Path("geometry_notes.pdf"),
}


st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(217, 119, 6, 0.18), transparent 30%),
            radial-gradient(circle at top right, rgba(15, 118, 110, 0.16), transparent 28%),
            linear-gradient(180deg, #f8fafc 0%, #fff7ed 45%, #f8fafc 100%);
        color: #172554 !important;
    }
    .stApp p, .stApp label, div[data-testid="stWidgetLabel"] p, .stApp h1, .stApp h2, .stApp h3, .stApp span, .stApp li {
        color: #172554 !important;
    }
    .hero {
        padding: 1.6rem 1.8rem;
        border-radius: 24px;
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(148, 163, 184, 0.25);
        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
        color: #0f172a;
    }
    .hero h1, .hero h2, .hero h3, .hero p {
        color: #0f172a;
    }
    .metric-card {
        padding: 1rem 1.1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.76);
        border: 1px solid rgba(148, 163, 184, 0.20);
        color: #0f172a;
    }
    .metric-card strong, .metric-card span, .metric-card div {
        color: #0f172a;
    }
    .evidence-card {
        padding: 1rem 1.1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.88);
        border-left: 6px solid #0f766e;
        margin-bottom: 0.9rem;
        color: #0f172a;
    }
    .evidence-card strong, .evidence-card span, .evidence-card div {
        color: #0f172a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1 style="margin-bottom:0.4rem;">Cogni Chunk 📚</h1>
        <p style="font-size:1.05rem; margin-bottom:0.25rem;">
            A personal project for document retrieval that can answer questions from long-form markdown notes and PDF study material,
            then show the evidence behind every result.
        </p>
        <p style="color:#475569; margin:0;">
            Focus areas: structure-aware chunking, PDF-aware ingestion, grounded retrieval, and a clean product experience ✨
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

selected_document_name = st.selectbox("📁 Choose a source document", list(DOCUMENTS))
doc_path = DOCUMENTS[selected_document_name]
analyst = TechnicalDocAnalyst(doc_path)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(
        f"<div class='metric-card'><strong>{len(analyst.chunks)}</strong><br/>📦 Structured sections indexed</div>",
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        "<div class='metric-card'><strong>🧠 Hybrid-style scoring</strong><br/>Heading, term, and evidence-aware ranking</div>",
        unsafe_allow_html=True,
    )
with col3:
    st.markdown(
        "<div class='metric-card'><strong>🔎 Explainable output</strong><br/>Confidence plus top evidence blocks</div>",
        unsafe_allow_html=True,
    )

st.write("")

examples = [
    "Why did retrieval latency improve by about 40 percent in release AKF-2.3?",
    "What happens when the vector index is unavailable?",
    "Why were write-heavy dashboards slower during the replica failover test?",
    "How does Atlas handle ingestion storms during large document migrations?",
]
geometry_examples = [
    "What is the relationship between an inscribed angle and its intercepted arc?",
    "How do you prove two triangles are similar using parallel lines?",
    "What are the properties of the diagonals of a square?",
    "How does the altitude to the hypotenuse behave in a right triangle?",
]

examples = examples if doc_path.suffix.lower() == ".md" else geometry_examples

selected_example = st.selectbox("💬 Demo query", options=["Custom question"] + examples)
default_query = "" if selected_example == "Custom question" else selected_example
query = st.text_input(
    "❓ Ask a question about the current document",
    value=default_query,
    placeholder="Example: What is the relationship between an inscribed angle and its intercepted arc?",
)

left, right = st.columns([1.5, 1.0])

with right:
    st.subheader("📝 Project Notes")
    st.write(
        "Use this panel to explain what makes the project credible: visible evidence, grounded answers, and support for both markdown and PDF sources."
    )
    st.caption(f"Source file: {doc_path.resolve()}")
    with st.expander("🚀 What the app is demonstrating"):
        st.markdown(
            "- Structured section parsing from Markdown\n"
            "- Page-aware extraction from PDFs\n"
            "- Lightweight retrieval without external APIs\n"
            "- Confidence labeling and evidence previews\n"
            "- A UI that makes the retrieval flow easy to understand and present"
        )

with left:
    if query:
        response = analyst.answer(query)
        st.subheader("✅ Answer")
        st.write(response["answer"])
        st.caption(f"Confidence: {response['confidence'].upper()} ⭐")

        st.subheader("📌 Top Evidence")
        for index, result in enumerate(response["results"], start=1):
            preview = textwrap.shorten(
                " ".join(result.chunk.content.split()),
                width=320,
                placeholder="...",
            )
            st.markdown(
                f"""
                <div class="evidence-card">
                    <strong>{index}. {result.chunk.heading_path}</strong><br/>
                    Score: {result.score:.3f}<br/>
                    Matched terms: {", ".join(result.matched_terms)}<br/><br/>
                    {preview}
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Enter a question or choose a demo query to see the retrieval pipeline in action ⚡")

with st.expander("📄 Preview of indexed source content"):
    st.text(analyst.document_text[:3000] + "\n...")
