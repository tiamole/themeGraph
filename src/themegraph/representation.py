"""Fail-closed authorization for human-facing statements, marks, and exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from themegraph.admissibility import (
    POLICY_VERSION,
    SUPPORTED_POLICY_VERSIONS,
    ClaimType,
    Decision,
    VisualEncoding,
)
from themegraph.models import AnalysisResult

STRUCTURAL_CERTIFICATE_GUARDED_ENTRY_POINTS = (
    "analysis-result serialization",
    "CLI structural export",
)

SEMANTIC_CERTIFICATE_GUARDED_ENTRY_POINTS = (
    "governed-representation API",
    "requested-claim export API",
    "inspector statement rendering",
    "inspector graph-mark rendering",
    "inspector requested-claim export",
    "publication representation enforcement",
)

COMPLETE_MEDIATION_ENTRY_POINTS = (
    STRUCTURAL_CERTIFICATE_GUARDED_ENTRY_POINTS
    + SEMANTIC_CERTIFICATE_GUARDED_ENTRY_POINTS
)

_REQUIRED_CERTIFICATE_FIELDS = frozenset(
    {
        "policy_version",
        "claim_type",
        "decision",
        "allowed_encoding",
        "allowed_statement",
        "allowed_export",
        "requested_representation_authorized",
        "fallback_claim",
        "witness",
    }
)


def validate_certificate_payload(certificate: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete or internally inconsistent output authorization."""
    missing = _REQUIRED_CERTIFICATE_FIELDS - certificate.keys()
    if missing:
        raise ValueError(f"Certificate lacks required fields: {sorted(missing)}")
    if certificate["policy_version"] not in SUPPORTED_POLICY_VERSIONS:
        raise ValueError("Certificate uses an unsupported policy version")
    claim_type = ClaimType(certificate["claim_type"])
    decision = Decision(certificate["decision"])
    encoding = VisualEncoding(certificate["allowed_encoding"])
    if not str(certificate["allowed_statement"]).strip():
        raise ValueError("Certificate does not authorize a statement class")
    if decision is Decision.REFUSE:
        if certificate["requested_representation_authorized"]:
            raise ValueError("Refused certificate authorizes the requested representation")
        if certificate["allowed_export"]:
            raise ValueError("Refused certificate authorizes requested-claim export")
        if encoding is VisualEncoding.DIRECTED_ARROW:
            raise ValueError("Refused certificate authorizes a semantic arrow")
    if decision is Decision.ADMIT and not certificate[
        "requested_representation_authorized"
    ]:
        raise ValueError("Admitted certificate blocks its requested representation")
    if encoding is VisualEncoding.DIRECTED_ARROW and decision is not Decision.ADMIT:
        raise ValueError("A semantic arrow requires an admitted certificate")
    if certificate["fallback_claim"] is not None:
        ClaimType(certificate["fallback_claim"])
    if not isinstance(certificate["witness"], (list, tuple)):
        raise TypeError("Certificate witness must be a serialized sequence")
    if certificate["policy_version"] == POLICY_VERSION and not certificate["witness"]:
        raise ValueError("Active-policy certificate lacks a decision witness")
    return certificate | {"claim_type": claim_type.value}


def certificate_for_claim(
    result: AnalysisResult, requested_claim: ClaimType | str
) -> dict[str, Any]:
    """Select exactly one valid certificate for a declared requested claim."""
    claim_type = ClaimType(requested_claim)
    matches = [
        certificate
        for certificate in result.claim_certificates
        if certificate.get("claim_type") == claim_type.value
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one certificate for {claim_type.value}; found {len(matches)}"
        )
    return validate_certificate_payload(matches[0])


def validate_certificate_collection(result: AnalysisResult) -> None:
    """Require one valid active certificate for every declared claim."""
    observed = [
        validate_certificate_payload(certificate)["claim_type"]
        for certificate in result.claim_certificates
    ]
    expected = [claim_type.value for claim_type in ClaimType]
    if sorted(observed) != sorted(expected):
        raise ValueError("Analysis result does not contain one certificate per claim")


# certificate-guarded-output-entry-point: governed-representation API; guard=certificate_for_claim
def governed_representation(
    result: AnalysisResult, requested_claim: ClaimType | str
) -> dict[str, Any]:
    """Derive a statement and mark only from the requested claim's certificate."""
    certificate = certificate_for_claim(result, requested_claim)
    encoding = VisualEncoding(certificate["allowed_encoding"])
    raw_edges = [edge.as_dict() for edge in result.edges]
    if encoding is VisualEncoding.NO_RELATION:
        edges: list[dict[str, Any]] = []
    elif encoding is VisualEncoding.UNDIRECTED_LINK:
        seen: set[tuple[str, str]] = set()
        edges = []
        for edge in raw_edges:
            term_a, term_b = sorted((edge["source"], edge["target"]))
            pair = (term_a, term_b)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(
                {
                    "term_a": term_a,
                    "term_b": term_b,
                    "relation_type": ClaimType.LEXICAL_ASSOCIATION.value,
                    "support": edge["support"],
                    "lift": edge["lift"],
                    "evidence": edge["evidence"],
                }
            )
    else:
        edges = raw_edges
    return {
        "corpus_name": result.corpus_name,
        "requested_claim": certificate["claim_type"],
        "decision": certificate["decision"],
        "exported_claim": (
            certificate["fallback_claim"]
            if certificate["decision"] == Decision.REFUSE.value
            else certificate["claim_type"]
        ),
        "visual_encoding": certificate["allowed_encoding"],
        "allowed_statement": certificate["allowed_statement"],
        "requested_claim_export_allowed": certificate["allowed_export"],
        "certificate": certificate,
        "nodes": result.nodes,
        "edges": edges,
    }


# certificate-guarded-output-entry-point: requested-claim export API; guard=governed_representation
def export_requested_claim(
    result: AnalysisResult,
    path: str | Path,
    requested_claim: ClaimType | str,
) -> None:
    """Export a requested claim only when its certificate permits that export."""
    representation = governed_representation(result, requested_claim)
    if not representation["requested_claim_export_allowed"]:
        raise PermissionError("The active certificate blocks requested-claim export")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(representation, indent=2, ensure_ascii=True), encoding="utf-8"
    )
