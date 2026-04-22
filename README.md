# Cogni Chunk: Personal Project for Technical Document Analysis

Cogni Chunk is a polished personal project focused on technical document retrieval, grounded answers, and a clean interactive experience. It combines a presentable Streamlit UI, a structured notebook walkthrough, and a richer technical source document so the project feels substantial rather than toy-sized.

## What This Demo Shows

- Structure-aware chunking from a long Markdown technical dossier
- Grounded retrieval with visible evidence instead of opaque answers
- A lightweight, self-contained pipeline that runs locally without external APIs
- A stronger product narrative around latency, resilience, and explainability

## Files

- `Intelligent_Technical_Document_Analyst.ipynb`: polished walkthrough of the project pipeline
- `app.py`: Streamlit interface for live demos
- `rag_demo.py`: reusable retrieval and answer synthesis logic
- `technical_doc.md`: expanded technical dossier used as the indexed source

## Run The Streamlit UI

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run A Quick Query In Python

```python
from rag_demo import run_cli_query

print(run_cli_query("What happens when the vector index is unavailable?"))
```

## Open The Notebook

```bash
jupyter notebook Intelligent_Technical_Document_Analyst.ipynb
```

## Suggested Demo Questions

- Why did retrieval latency improve by about 40 percent in release AKF-2.3?
- What happens when the vector index is unavailable?
- Why were write-heavy dashboards slower during the replica failover test?
- How does Atlas handle ingestion storms during large document migrations?

## Project Framing

The strongest pitch is:

1. Start with the pain: technical docs are dense and naive search misses intent.
2. Show the approach: preserve document structure, retrieve relevant sections, and ground the answer in evidence.
3. Close on product quality: confidence signals, observable behavior, and a UI that helps people trust the result.
