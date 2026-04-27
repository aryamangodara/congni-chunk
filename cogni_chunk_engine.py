from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, List, TypedDict

import nltk
from nltk.corpus import stopwords
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph, START, END

nltk.download("stopwords", quiet=True)
STOPWORDS = set(stopwords.words("english"))


def tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9\-]+", text.lower()) if token not in STOPWORDS]


def build_ngrams(tokens: List[str], size: int = 2) -> set[str]:
    return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def split_markdown_sections(markdown_text: str) -> List[Document]:
    sections, stack, lines = [], [], []

    def flush_section() -> None:
        content = "\n".join(lines).strip()
        if content and len(tokenize(content)) > 0:
            title = stack[-1] if stack else "Document Overview"
            sections.append(Document(page_content=content, metadata={"title": title, "heading_path": " > ".join(stack) or title}))
        lines.clear()

    for raw_line in markdown_text.splitlines():
        if match := re.match(r"^(#{1,6})\s+(.*)$", raw_line.rstrip()):
            flush_section()
            stack = stack[:len(match.group(1)) - 1] + [match.group(2).strip()]
        else:
            lines.append(raw_line.rstrip())

    flush_section()
    return sections


class ResearcherAgent:
    """Analytical module used by the researcher node."""
    def __init__(self, docs: List[Document]):
        self.docs = docs
        self._idf = self._compute_idf(self.docs)

    @staticmethod
    def _compute_idf(docs: Iterable[Document]) -> dict[str, float]:
        freqs = Counter(token for doc in docs for token in set(tokenize(f"{doc.metadata.get('heading_path', '')} {doc.page_content}")))
        return {tok: math.log((1 + len(list(docs))) / (1 + freq)) + 1.0 for tok, freq in freqs.items()}

    def is_reference_section(self, doc: Document) -> bool:
        return any(m in doc.metadata.get('heading_path', '').lower() for m in ["sample questions", "project presentation notes", "closing notes"])

    def search(self, query: str, top_k: int = 4) -> List[dict]:
        q_tokens, q_bigrams = tokenize(query), build_ngrams(tokenize(query), size=2)
        results: List[dict] = []
        
        for doc in self.docs:
            heading = doc.metadata.get('heading_path', '')
            haystack = f"{heading}\n{doc.page_content}".lower()
            c_tokens = tokenize(haystack)
            
            if not c_tokens or not (matched := sorted(set(q_tokens) & set(c_tokens))):
                continue

            c_len = len(c_tokens)
            score = sum((c_tokens.count(t) / c_len) * self._idf.get(t, 1.0) + (0.35 if t in heading.lower() else 0) + (0.12 if self._idf.get(t, 1.0) > 2.6 else 0) for t in matched)
            score += 0.08 if any(p in haystack for p in ["because", "falls back to", "results in", "latency", "fails", "incident", "theorem", "proof", "therefore"]) else 0.0
            score += (len(matched) / len(set(q_tokens))) * 0.18 + len(q_bigrams & build_ngrams(c_tokens, size=2)) * 0.22 + min(c_len, 160) / 4000
            score *= 0.35 if self.is_reference_section(doc) else 1.0
            
            results.append({"doc": doc, "score": score, "matched_terms": matched})

        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]


class AgentState(TypedDict):
    query: str
    retrieved_docs: List[dict]
    answer: str
    confidence: str


class MultiAgentSystem:
    def __init__(self, document_path: str | Path):
        self.document_path = Path(document_path)
        self.document_text, self.docs = self._load_document(self.document_path)
        self.researcher = ResearcherAgent(self.docs)
        self.workflow = self._build_graph()

    def _load_document(self, path: Path) -> tuple[str, List[Document]]:
        if path.suffix.lower() == ".pdf":
            loader = PyPDFLoader(str(path))
            pages = loader.load()
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
            pdf_docs = text_splitter.split_documents(pages)
            for i, doc in enumerate(pdf_docs, 1):
                doc.metadata["title"] = f"{path.stem.replace('_', ' ').title()} - Segment {i}"
                doc.metadata["heading_path"] = f"{path.stem.replace('_', ' ').title()} > Segment {i}"
            raw_text = "\n".join(page.page_content for page in pages)
            return raw_text, pdf_docs
        else:
            text = path.read_text(encoding="utf-8")
            return text, split_markdown_sections(text)

    def _build_graph(self):
        def research_node(state: AgentState):
            return {"retrieved_docs": self.researcher.search(state["query"], top_k=4)}

        def writer_node(state: AgentState):
            results = state.get("retrieved_docs", [])
            if not results:
                return {"answer": "I could not find grounded evidence for that query in the current documents.", "confidence": "LOW"}

            top_score = results[0]["score"]
            valid = [r for r in results if r["score"] >= top_score * 0.45 and not self.researcher.is_reference_section(r["doc"])] or [results[0]]

            evidence_lines: List[str] = []
            for r in valid[:3]:
                sentences = re.split(r"(?<=[.!?])\s+", r["doc"].page_content.replace("\n", " "))
                best = [s.strip() for s in sentences if any(t in s.lower() for t in r["matched_terms"])]
                evidence_lines.extend(best[:2] if best else [r["doc"].page_content.strip()][:2])

            titles = [r["doc"].metadata.get("title", "Section") for r in valid[:3]]
            answer = f"The strongest evidence points to '{titles[0]}'. {' '.join(evidence_lines[:4]).strip()} This answer is grounded in sections about {', '.join(titles)}."
            return {"answer": answer, "confidence": "HIGH" if top_score > 0.45 else "MEDIUM"}

        workflow = StateGraph(AgentState)
        workflow.add_node("researcher", research_node)
        workflow.add_node("writer", writer_node)
        workflow.add_edge(START, "researcher")
        workflow.add_edge("researcher", "writer")
        workflow.add_edge("writer", END)
        return workflow.compile()

    def answer(self, query: str) -> dict:
        result = self.workflow.invoke({"query": query})
        return {
            "answer": result.get("answer", ""),
            "results": result.get("retrieved_docs", []),
            "confidence": result.get("confidence", "LOW")
        }


def run_cli_query(query: str, document_path: str = "technical_doc.md") -> str:
    system = MultiAgentSystem(document_path)
    response = system.answer(query)
    lines = [
        f"Document: {document_path}",
        f"Query: {query}",
        f"Confidence: {response['confidence']}",
        "",
        response["answer"],
        "",
        "Top Evidence:",
    ]
    for index, result in enumerate(response["results"], start=1):
        doc = result["doc"]
        preview = doc.page_content.replace("\n", " ")
        preview = re.sub(r"\s+", " ", preview).strip()
        heading_path = doc.metadata.get("heading_path", "")
        lines.append(
            f"{index}. {heading_path} | score={result['score']:.3f} | matched={', '.join(result['matched_terms'])}"
        )
        lines.append(f"   {preview[:240]}...")
    return "\n".join(lines)
