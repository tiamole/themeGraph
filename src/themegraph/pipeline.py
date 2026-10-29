"""End-to-end analysis pipeline with explicit configuration and JSON export."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from themegraph.admissibility import EvidenceBundle, EvidenceChannel, evaluate_all_claims
from themegraph.graph import DirectedGraph
from themegraph.models import AnalysisResult, DocumentRecord
from themegraph.relations import ConditionalAssociationExtractor
from themegraph.representation import validate_certificate_collection
from themegraph.text import RegexUnitExtractor


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in sorted(value) if item is not None]
    return value


def analyze_documents(
    documents: Iterable[DocumentRecord],
    corpus_name: str,
    unit_extractor: RegexUnitExtractor | None = None,
    relation_extractor: ConditionalAssociationExtractor | None = None,
) -> AnalysisResult:
    unit_extractor = unit_extractor or RegexUnitExtractor()
    relation_extractor = relation_extractor or ConditionalAssociationExtractor()
    materialized_documents = list(documents)
    units = unit_extractor.extract(materialized_documents)
    vocabulary, edges = relation_extractor.extract(units)
    graph = DirectedGraph.from_edges(
        ((edge.source, edge.target) for edge in edges), nodes=vocabulary
    )
    components = graph.strongly_connected_components()
    weak_components = graph.weakly_connected_components()
    condensed, membership = graph.condensation(components)
    condensation_edges = sorted(
        (int(source), int(target))
        for source, targets in condensed.adjacency.items()
        for target in targets
    )
    observed_channels = (
        frozenset({EvidenceChannel.CO_OCCURRENCE}) if units else frozenset()
    )
    provenance_complete = bool(materialized_documents) and all(
        document.provenance.strip() for document in materialized_documents
    )
    certificates = evaluate_all_claims(
        EvidenceBundle(
            channels=observed_channels,
            provenance_complete=provenance_complete,
        )
    )
    return AnalysisResult(
        corpus_name=corpus_name,
        document_count=len(materialized_documents),
        unit_count=len(units),
        nodes=sorted(str(node) for node in graph.nodes),
        edges=edges,
        components=[frozenset(str(node) for node in component) for component in components],
        weak_components=[
            frozenset(str(node) for node in component) for component in weak_components
        ],
        condensation_edges=condensation_edges,
        bridge_scores={
            str(node): score for node, score in graph.bridge_nodes(membership).items()
        },
        claim_certificates=[certificate.as_dict() for certificate in certificates],
        configuration={
            "unit_extractor": _json_safe(asdict(unit_extractor)),
            "relation_extractor": _json_safe(asdict(relation_extractor)),
            "admissibility_policy_version": certificates[0].policy_version,
            "edge_semantics": "A -> B means B occurs in a configured fraction of units containing A, with minimum lift over B prevalence.",
        },
    )


# certificate-guarded-output-entry-point: analysis-result serialization; guard=validate_certificate_collection
def export_result(result: AnalysisResult, path: str | Path) -> None:
    validate_certificate_collection(result)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.as_dict(), indent=2, ensure_ascii=True), encoding="utf-8"
    )