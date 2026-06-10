# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Cogni Chunk is a self-contained document Q&A demo (portfolio project). It answers questions over a Markdown dossier (`technical_doc.md`) and a PDF (`geometry_notes.pdf`) using purely lexical TF-IDF-style retrieval — there is **no LLM, no embeddings, no vector DB, and no external API**, despite the "multi-agent RAG" framing. LangGraph is used only to structure a two-node pipeline (researcher → writer).

## Commands

```bash
pip install -r requirements.txt
streamlit run app.py                 # interactive UI

# quick CLI smoke test (no test suite exists)
python -c "from cogni_chunk_engine import run_cli_query; print(run_cli_query('What happens when the vector index is unavailable?'))"
python -c "from cogni_chunk_engine import run_cli_query; print(run_cli_query('What is the relationship between an inscribed angle and its intercepted arc?', 'geometry_notes.pdf'))"
```

There is no linter, formatter config, or test framework. Verify changes by running the CLI queries above and booting the Streamlit app.

## Architecture

- **`cogni_chunk_engine.py`** — all logic. `MultiAgentSystem(document_path)` loads a document (Markdown → heading-based sections via `split_markdown_sections`; PDF → `PyPDFLoader` + `RecursiveCharacterTextSplitter`, 500/50), then compiles a LangGraph `StateGraph` with two nodes:
  - *researcher*: `ResearcherAgent.search()` — hand-tuned scoring: IDF-weighted term frequency, heading-match boost, bigram overlap, causal-phrase bonus, and a 0.35× penalty for "reference" sections (sample questions, presentation notes, closing notes).
  - *writer*: extracts sentences containing matched terms from top chunks and templates them into an answer with a HIGH/MEDIUM/LOW confidence label.
  - Every chunk carries `title` and `heading_path` metadata; the scorer and UI both depend on `heading_path`.
- **`app.py`** — Streamlit UI. Wraps engine construction in `@st.cache_resource` (keyed by path string) — keep this, the PDF parse and IDF build are slow per rerun. Document choices and demo queries are hardcoded in `DOCUMENTS` / `examples` / `geometry_examples`.
- **`Intelligent_Technical_Document_Analyst.ipynb`** — a deliberately self-contained **duplicate** of the engine code (it imports nothing from `cogni_chunk_engine.py`). Any bug fix or behavior change in the engine's `ResearcherAgent`, `split_markdown_sections`, or writer logic must be mirrored in the corresponding notebook cells. Edit the notebook programmatically (JSON) rather than by hand.

## Constraints

- Keep the project runnable offline: stopword loading has a built-in fallback set for when the NLTK download fails — don't reintroduce a hard network dependency.
- Scoring thresholds (e.g. `score * 0.45` validity cutoff, `0.45` HIGH-confidence cutoff) are tuned to the two bundled documents; changing them shifts demo answers, so re-run the demo queries after touching scoring.
- Environment quirk: developed on Python 3.14, where `langchain-core` warns about Pydantic V1 compatibility. It works, but LangChain upgrades may break — keep the `<1` pins in `requirements.txt` unless verified.
