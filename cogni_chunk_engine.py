from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re
from collections import Counter
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
    sections, stack, lines = [], [], []

    def flush_section() -> None:
        content = "\n".join(lines).strip()
        if content and (chunk := chunk_from_text(stack[-1] if stack else "Document Overview", " > ".join(stack) if stack else "Document Overview", content)):
            sections.append(chunk)
        lines.clear()

    for raw_line in markdown_text.splitlines():
        if match := re.match(r"^(#{1,6})\s+(.*)$", raw_line.rstrip()):
            flush_section()
            stack = stack[:len(match.group(1)) - 1] + [match.group(2).strip()]
        else:
            lines.append(raw_line.rstrip())

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
        docs = list(chunks)
        freqs = Counter(token for c in docs for token in set(tokenize(f"{c.heading_path} {c.content}")))
        return {tok: math.log((1 + len(docs)) / (1 + freq)) + 1.0 for tok, freq in freqs.items()}

    def search(self, query: str, top_k: int = 4) -> List[SearchResult]:
        q_tokens, q_bigrams = tokenize(query), build_ngrams(tokenize(query), size=2)
        results: List[SearchResult] = []
        
        for chunk in self.chunks:
            haystack = f"{chunk.heading_path}\n{chunk.content}".lower()
            c_tokens = tokenize(haystack)
            
            if not c_tokens or not (matched := sorted(set(q_tokens) & set(c_tokens))):
                continue

            c_len = len(c_tokens)
            score = sum((c_tokens.count(t) / c_len) * self._idf.get(t, 1.0) + (0.35 if t in chunk.heading_path.lower() else 0) + (0.12 if self._idf.get(t, 1.0) > 2.6 else 0) for t in matched)
            score += 0.08 if any(p in haystack for p in ["because", "falls back to", "results in", "latency", "fails", "incident", "theorem", "proof", "therefore"]) else 0.0
            score += (len(matched) / len(set(q_tokens))) * 0.18 + len(q_bigrams & build_ngrams(c_tokens, size=2)) * 0.22 + min(c_len, 160) / 4000
            score *= 0.35 if is_reference_section(chunk) else 1.0
            
            results.append(SearchResult(chunk=chunk, score=score, matched_terms=matched))

        return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]

    def answer(self, query: str, top_k: int = 4) -> dict:
        results = self.search(query, top_k=top_k)
        if not results:
            return {"answer": "I could not find grounded evidence for that query in the current document.", "results": [], "confidence": "low"}

        top_score = results[0].score
        valid = [r for r in results if r.score >= top_score * 0.45 and not is_reference_section(r.chunk)] or [results[0]]

        evidence_lines: List[str] = []
        for r in valid[:3]:
            sentences = re.split(r"(?<=[.!?])\s+", r.chunk.content.replace("\n", " "))
            best = [s.strip() for s in sentences if any(t in s.lower() for t in r.matched_terms)]
            evidence_lines.extend(best[:2] if best else [r.chunk.content.strip()][:2])

        titles = [r.chunk.title for r in valid[:3]]
        answer = f"The strongest evidence points to '{titles[0]}'. {' '.join(evidence_lines[:4]).strip()} This answer is grounded in sections about {', '.join(titles)}."
        return {"answer": answer, "results": results, "confidence": "high" if top_score > 0.45 else "medium"}


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
