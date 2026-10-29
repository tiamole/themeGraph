"""Typed records shared across corpus, relation, and export layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    document_id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
    provenance: str = ""


@dataclass(frozen=True, slots=True)
class TextUnit:
    unit_id: str
    document_id: str
    text: str
    terms: frozenset[str]
    provenance_source: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    unit_id: str
    document_id: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class RelationEdge:
    source: str
    target: str
    relation_type: str
    confidence: float
    support: int
    lift: float
    document_support: int = 0
    source_support: int = 0
    effective_support_lower_bound: int = 0
    evidence: tuple[EvidenceRecord, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "support": self.support,
            "lift": self.lift,
            "document_support": self.document_support,
            "source_support": self.source_support,
            "effective_support_lower_bound": self.effective_support_lower_bound,
            "evidence": [
                {
                    "unit_id": item.unit_id,
                    "document_id": item.document_id,
                    "excerpt": item.excerpt,
                }
                for item in self.evidence
            ],
        }


@dataclass(slots=True)
class AnalysisResult:
    corpus_name: str
    document_count: int
    unit_count: int
    nodes: list[str]
    edges: list[RelationEdge]
    components: list[frozenset[str]]
    weak_components: list[frozenset[str]]
    condensation_edges: list[tuple[int, int]]
    bridge_scores: dict[str, int]
    claim_certificates: list[dict[str, Any]]
    configuration: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.0",
            "corpus_name": self.corpus_name,
            "document_count": self.document_count,
            "unit_count": self.unit_count,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": self.nodes,
            "edges": [edge.as_dict() for edge in self.edges],
            "components": [sorted(component) for component in self.components],
            "weak_components": [sorted(component) for component in self.weak_components],
            "condensation_edges": [list(edge) for edge in self.condensation_edges],
            "bridge_scores": self.bridge_scores,
            "claim_certificates": self.claim_certificates,
            "configuration": self.configuration,
        }
