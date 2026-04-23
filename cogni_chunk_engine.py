from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re
from typing import Iterable, List

from pypdf import PdfReader


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


def build_ngrams(tokens: List[str], size: int = 2) -> set[str]:
    return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def chunk_from_text(title: str, heading_path: str, content: str) -> Chunk | None:
    normalized = content.strip()
    token_count = len(tokenize(normalized))
    if not normalized or token_count == 0:
        return None
    return Chunk(
        title=title,
        heading_path=heading_path,
        content=normalized,
        token_count=token_count,
    )


def split_markdown_sections(markdown_text: str) -> List[Chunk]:
    sections: List[Chunk] = []
    heading_stack: List[str] = []
    current_lines: List[str] = []

    def flush_section() -> None:
        if not current_lines:
            return
        chunk = chunk_from_text(
            title=heading_stack[-1] if heading_stack else "Document Overview",
            heading_path=" > ".join(heading_stack) if heading_stack else "Document Overview",
            content="\n".join(current_lines),
        )
        current_lines.clear()
        if chunk:
            sections.append(chunk)

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
    return sections


def split_pdf_sections(document_path: Path) -> tuple[str, List[Chunk]]:
    reader = PdfReader(str(document_path))
    page_texts: List[str] = []
    cleaned_pages: List[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        normalized_page = re.sub(r"\r\n?", "\n", extracted).strip()
        if not normalized_page:
            continue
        normalized_page = re.sub(
            r"Geometry Notes Compendium\s+\|\s+Page\s+\d+\s+of\s+\d+",
            "",
            normalized_page,
            flags=re.IGNORECASE,
        ).strip()
        page_texts.append(f"Page {page_number}\n{normalized_page}")
        cleaned_pages.append(normalized_page)

    combined_text = "\n".join(cleaned_pages).strip()
    heading_pattern = re.compile(r"(?m)^(?P<label>\d+\.\s+[A-Z][A-Z0-9,\- ]+)$")
    matches = list(heading_pattern.finditer(combined_text))
    sections: List[Chunk] = []

    if matches:
        document_title = "Document Overview"
        lead_in = combined_text[: matches[0].start()].strip()
        if lead_in:
            first_line = lead_in.splitlines()[0].strip()
            if first_line:
                document_title = first_line.title()
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(combined_text)
            heading = match.group("label").strip()
            body = combined_text[start:end].strip()
            chunk = chunk_from_text(
                title=heading.title(),
                heading_path=f"{document_title} > {heading.title()}",
                content=body,
            )
            if chunk:
                sections.append(chunk)
    else:
        blocks = [block.strip() for block in re.split(r"\n\s*\n", combined_text) if len(tokenize(block)) >= 35]
        for block_index, block in enumerate(blocks, start=1):
            chunk = chunk_from_text(
                title=f"Page Segment {block_index}",
                heading_path=f"{document_path.stem} > Segment {block_index}",
                content=block,
            )
            if chunk:
                sections.append(chunk)

    return "\n\n".join(page_texts), sections


def load_document(document_path: str | Path) -> tuple[str, List[Chunk]]:
    path = Path(document_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return split_pdf_sections(path)
    text = path.read_text(encoding="utf-8")
    return text, split_markdown_sections(text)


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
        self.document_text, self.chunks = load_document(self.document_path)
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
        query_bigrams = build_ngrams(query_tokens, size=2)
        results: List[SearchResult] = []
        for chunk in self.chunks:
            haystack = f"{chunk.heading_path}\n{chunk.content}".lower()
            chunk_tokens = tokenize(haystack)
            if not chunk_tokens:
                continue
            chunk_token_set = set(chunk_tokens)
            chunk_bigrams = build_ngrams(chunk_tokens, size=2)
            matched_terms = sorted({token for token in query_tokens if token in chunk_token_set})
            if not matched_terms:
                continue

            score = 0.0
            for token in matched_terms:
                tf = chunk_tokens.count(token) / max(len(chunk_tokens), 1)
                score += tf * self._idf.get(token, 1.0)
                if token in chunk.heading_path.lower():
                    score += 0.35
                if self._idf.get(token, 1.0) > 2.6:
                    score += 0.12
            if any(
                phrase in haystack
                for phrase in [
                    "because",
                    "falls back to",
                    "results in",
                    "latency",
                    "fails",
                    "incident",
                    "theorem",
                    "proof",
                    "therefore",
                ]
            ):
                score += 0.08
            score += (len(matched_terms) / max(len(set(query_tokens)), 1)) * 0.18
            matched_bigrams = query_bigrams & chunk_bigrams
            score += len(matched_bigrams) * 0.22
            score += min(chunk.token_count, 160) / 4000
            if is_reference_section(chunk):
                score *= 0.35
            results.append(SearchResult(chunk=chunk, score=score, matched_terms=matched_terms))

        return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]

    def answer(self, query: str, top_k: int = 4) -> dict:
        results = self.search(query, top_k=top_k)
        if not results:
            return {
                "answer": "I could not find grounded evidence for that query in the current document.",
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
        f"Document: {document_path}",
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
