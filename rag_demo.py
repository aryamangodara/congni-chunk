from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re
from typing import Iterable, List


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "what",
    "when",
    "why",
    "with",
}


@dataclass
class Chunk:
    title: str
    heading_path: str
    content: str
    token_count: int


@dataclass
class SearchResult:
    chunk: Chunk
    score: float
    matched_terms: List[str]


def tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9\-]+", text.lower()) if token not in STOPWORDS]


def split_markdown_sections(markdown_text: str) -> List[Chunk]:
    sections: List[Chunk] = []
    heading_stack: List[str] = []
    current_lines: List[str] = []

    def flush_section() -> None:
        if not current_lines:
            return
        content = "\n".join(current_lines).strip()
        current_lines.clear()
        if not content:
            return
        heading_path = " > ".join(heading_stack) if heading_stack else "Document Overview"
        title = heading_stack[-1] if heading_stack else "Document Overview"
        sections.append(
            Chunk(
                title=title,
                heading_path=heading_path,
                content=content,
                token_count=len(tokenize(content)),
            )
        )

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            flush_section()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(title)
            continue
        current_lines.append(line)

    flush_section()
    return [section for section in sections if section.token_count > 0]


def is_reference_section(chunk: Chunk) -> bool:
    heading = chunk.heading_path.lower()
    return any(
        marker in heading
        for marker in [
            "sample questions",
            "project presentation notes",
            "closing notes",
        ]
    )


class TechnicalDocAnalyst:
    def __init__(self, document_path: str | Path):
        self.document_path = Path(document_path)
        self.document_text = self.document_path.read_text(encoding="utf-8")
        self.chunks = split_markdown_sections(self.document_text)
        self._idf = self._compute_idf(self.chunks)

    @staticmethod
    def _compute_idf(chunks: Iterable[Chunk]) -> dict[str, float]:
        doc_count = 0
        frequencies: dict[str, int] = {}
        for chunk in chunks:
            doc_count += 1
            for token in set(tokenize(f"{chunk.heading_path} {chunk.content}")):
                frequencies[token] = frequencies.get(token, 0) + 1
        return {
            token: math.log((1 + doc_count) / (1 + freq)) + 1.0
            for token, freq in frequencies.items()
        }

    def search(self, query: str, top_k: int = 4) -> List[SearchResult]:
        query_tokens = tokenize(query)
        results: List[SearchResult] = []
        for chunk in self.chunks:
            haystack = f"{chunk.heading_path}\n{chunk.content}".lower()
            chunk_tokens = tokenize(haystack)
            if not chunk_tokens:
                continue
            matched_terms = sorted({token for token in query_tokens if token in haystack})
            if not matched_terms:
                continue

            score = 0.0
            for token in matched_terms:
                tf = chunk_tokens.count(token) / max(len(chunk_tokens), 1)
                score += tf * self._idf.get(token, 1.0)
                if token in chunk.heading_path.lower():
                    score += 0.35
            if any(phrase in haystack for phrase in ["because", "falls back to", "results in", "latency", "fails", "incident"]):
                score += 0.08
            score += min(chunk.token_count, 160) / 4000
            if is_reference_section(chunk):
                score *= 0.35
            results.append(SearchResult(chunk=chunk, score=score, matched_terms=matched_terms))

        return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]

    def answer(self, query: str, top_k: int = 4) -> dict:
        results = self.search(query, top_k=top_k)
        if not results:
            return {
                "answer": "I could not find grounded evidence for that query in the current technical document.",
                "results": [],
                "confidence": "low",
            }

        top_score = results[0].score
        grounded_results = [
            result for result in results if result.score >= top_score * 0.45 and not is_reference_section(result.chunk)
        ]
        if not grounded_results:
            grounded_results = [results[0]]

        evidence_lines: List[str] = []
        for result in grounded_results[:3]:
            sentences = re.split(r"(?<=[.!?])\s+", result.chunk.content.replace("\n", " "))
            best_sentences = [s.strip() for s in sentences if any(term in s.lower() for term in result.matched_terms)]
            if not best_sentences:
                best_sentences = [result.chunk.content.strip()]
            evidence_lines.extend(best_sentences[:2])

        condensed = " ".join(evidence_lines[:4]).strip()
        leading = grounded_results[0].chunk
        confidence = "high" if results[0].score > 0.45 else "medium"
        answer = (
            f"The strongest evidence points to '{leading.title}'. "
            f"{condensed} "
            f"This answer is grounded in sections about {', '.join(result.chunk.title for result in grounded_results[:3])}."
        )
        return {"answer": answer, "results": results, "confidence": confidence}


def run_cli_query(query: str, document_path: str = "technical_doc.md") -> str:
    analyst = TechnicalDocAnalyst(document_path)
    response = analyst.answer(query)
    lines = [
        f"Query: {query}",
        f"Confidence: {response['confidence']}",
        "",
        response["answer"],
        "",
        "Top Evidence:",
    ]
    for index, result in enumerate(response["results"], start=1):
        preview = result.chunk.content.replace("\n", " ")
        preview = re.sub(r"\s+", " ", preview).strip()
        lines.append(
            f"{index}. {result.chunk.heading_path} | score={result.score:.3f} | matched={', '.join(result.matched_terms)}"
        )
        lines.append(f"   {preview[:240]}...")
    return "\n".join(lines)
