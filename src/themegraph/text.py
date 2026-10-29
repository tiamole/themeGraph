"""Deterministic text-unit and candidate-term extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from themegraph.models import DocumentRecord, TextUnit

DEFAULT_STOPWORDS = frozenset(
    {
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
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "we",
        "will",
        "with",
        "you",
        "your",
    }
)


@dataclass(frozen=True, slots=True)
class RegexUnitExtractor:
    unit_mode: str = "sentence"
    min_token_length: int = 3
    include_bigrams: bool = True
    max_terms_per_unit: int = 30
    stopwords: frozenset[str] = DEFAULT_STOPWORDS

    sentence_pattern = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
    paragraph_pattern = re.compile(r"(?:\r?\n){2,}")
    token_pattern = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]*")

    def __post_init__(self) -> None:
        if self.unit_mode not in {"sentence", "paragraph", "sentence-window"}:
            raise ValueError(f"Unsupported unit mode: {self.unit_mode}")

    def _segments(self, text: str) -> list[str]:
        if self.unit_mode == "paragraph":
            return [
                segment.strip()
                for segment in self.paragraph_pattern.split(text)
                if segment.strip()
            ]
        sentences = [
            segment.strip()
            for segment in self.sentence_pattern.split(text)
            if segment.strip()
        ]
        if self.unit_mode == "sentence-window":
            if len(sentences) < 2:
                return sentences
            return [f"{left} {right}" for left, right in pairwise(sentences)]
        return sentences

    def _terms(self, text: str) -> frozenset[str]:
        tokens = [
            token.lower().strip(".-")
            for token in self.token_pattern.findall(text)
            if len(token.strip(".-")) >= self.min_token_length
            and token.lower().strip(".-") not in self.stopwords
        ]
        ordered_terms: list[str] = []
        seen: set[str] = set()
        candidates = list(tokens)
        if self.include_bigrams:
            candidates.extend(f"{left} {right}" for left, right in pairwise(tokens))
        for term in candidates:
            if term not in seen:
                seen.add(term)
                ordered_terms.append(term)
            if len(ordered_terms) >= self.max_terms_per_unit:
                break
        return frozenset(ordered_terms)

    def extract(self, documents: Iterable[DocumentRecord]) -> list[TextUnit]:
        units: list[TextUnit] = []
        for document in documents:
            segments = self._segments(document.text)
            for segment_index, segment in enumerate(segments, 1):
                terms = self._terms(segment)
                if terms:
                    units.append(
                        TextUnit(
                            unit_id=f"{document.document_id}:u{segment_index}",
                            document_id=document.document_id,
                            text=segment,
                            terms=terms,
                            provenance_source=document.provenance,
                        )
                    )
        return units
