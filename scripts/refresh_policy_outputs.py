"""Refresh policy-dependent fields without rerunning corpus extraction."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from themegraph.admissibility import (
    AdjudicationStatus,
    EvidenceBundle,
    EvidenceChannel,
    EvidenceRecord,
    GovernedObject,
    ObjectType,
    evaluate_all_claims,
)
from themegraph.benchmark import complete_benchmark

ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )


def _evidence_from_certificate(certificate: dict[str, Any]) -> EvidenceBundle:
    channels = frozenset(
        EvidenceChannel(channel)
        for channel in certificate.get("observed_channels", [])
    )
    governed_object_payload = certificate.get("governed_object")
    governed_object = None
    if isinstance(governed_object_payload, dict):
        governed_object = GovernedObject(
            source=str(governed_object_payload["source"]),
            source_type=ObjectType(governed_object_payload["source_type"]),
            target=str(governed_object_payload["target"]),
            target_type=ObjectType(governed_object_payload["target_type"]),
        )
    requested_relation_payload = certificate.get("requested_relation")
    requested_relation = (
        tuple(str(value) for value in requested_relation_payload)
        if governed_object is None
        and isinstance(requested_relation_payload, list)
        and len(requested_relation_payload) == 2
        else None
    )
    adjudication_status = (
        AdjudicationStatus.APPROVED
        if certificate.get("adjudication_approved", False)
        else AdjudicationStatus.NOT_REVIEWED
    )
    records = tuple(
        EvidenceRecord(
            channel=channel,
            relation=(governed_object.relation if governed_object else requested_relation),
            adjudication_status=adjudication_status,
        )
        for channel in channels
    )
    return EvidenceBundle(
        records=records,
        requested_relation=requested_relation,
        governed_object=governed_object,
        provenance_complete=bool(certificate.get("provenance_complete", False)),
        specification_survival=certificate.get("specification_survival"),
        uncertainty_adequate=bool(certificate.get("uncertainty_adequate", False)),
        dependence_adequate=bool(certificate.get("dependence_adequate", False)),
        counterevidence=tuple(certificate.get("counterevidence", [])),
        causal_method=str(certificate.get("causal_method", "")),
        causal_assumptions=tuple(certificate.get("causal_assumptions", [])),
        causal_estimand=str(certificate.get("causal_estimand", "")),
        causal_design=str(certificate.get("causal_design", "")),
        causal_diagnostics=str(certificate.get("causal_diagnostics", "")),
    )


def refresh_policy_outputs(root: Path = ROOT) -> list[Path]:
    summary_path = root / "results" / "research_evaluation_summary.json"
    summary = _read_json(summary_path)
    updated = []
    for corpus_name in sorted(summary["corpora"]):
        path = root / "results" / "evaluation_corpora" / f"{corpus_name}.json"
        payload = _read_json(path)
        existing = payload.get("claim_certificates", [])
        if not existing:
            raise ValueError(f"Missing claim certificates in {path}")
        evidence = _evidence_from_certificate(existing[0])
        if evidence.governed_object is None:
            evidence = replace(
                evidence,
                requested_relation=None,
                governed_object=GovernedObject(
                    source="<source-term>",
                    source_type=ObjectType.TERM,
                    target="<target-term>",
                    target_type=ObjectType.TERM,
                ),
            )
        certificates = evaluate_all_claims(evidence)
        payload["claim_certificates"] = [
            certificate.as_dict() for certificate in certificates
        ]
        payload.setdefault("configuration", {})[
            "admissibility_policy_version"
        ] = certificates[0].policy_version
        _write_json(path, payload)
        updated.append(path)

    benchmark = complete_benchmark()
    benchmark_path = root / "results" / "claim_admissibility_benchmark.json"
    _write_json(benchmark_path, benchmark)
    updated.append(benchmark_path)

    summary["claim_admissibility_benchmark"] = benchmark
    _write_json(summary_path, summary)
    updated.append(summary_path)
    return updated


if __name__ == "__main__":
    paths = refresh_policy_outputs()
    print(f"Refreshed policy-dependent fields in {len(paths)} files")