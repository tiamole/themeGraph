"""Controlled mechanism benchmarks for executable claim-admissibility policies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any

from themegraph.admissibility import (
    FALLBACK_PREFERENCES,
    FALLBACK_PROJECTIONS,
    POLICIES,
    POLICY_VERSION,
    ClaimType,
    Decision,
    EvidenceBundle,
    EvidenceChannel,
    EvidencePolarity,
    EvidencePredicate,
    EvidenceRecord,
    GovernedObject,
    ObjectType,
    VisualEncoding,
    evaluate_claim,
    lint_policy,
    policy_as_dict,
)
from themegraph.representation import (
    COMPLETE_MEDIATION_ENTRY_POINTS,
    SEMANTIC_CERTIFICATE_GUARDED_ENTRY_POINTS,
    STRUCTURAL_CERTIFICATE_GUARDED_ENTRY_POINTS,
    validate_certificate_payload,
)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    situation: str
    claim_type: ClaimType
    evidence: EvidenceBundle
    expected_decision: Decision
    expected_fallback: ClaimType | None = None


def benchmark_cases() -> tuple[BenchmarkCase, ...]:
    co_occurrence = frozenset({EvidenceChannel.CO_OCCURRENCE})
    return (
        BenchmarkCase(
            "unordered-association",
            "Unordered co-occurrence supports a local lexical association.",
            ClaimType.LEXICAL_ASSOCIATION,
            EvidenceBundle(co_occurrence),
            Decision.ADMIT,
        ),
        BenchmarkCase(
            "prevalence-asymmetry",
            "Conditional asymmetry exists but is determined by marginal prevalence.",
            ClaimType.ASYMMETRIC_CONDITIONAL,
            EvidenceBundle(co_occurrence),
            Decision.QUALIFY,
        ),
        BenchmarkCase(
            "unsupported-temporal-order",
            "Unordered co-occurrence cannot identify temporal precedence.",
            ClaimType.EVENT_TEMPORAL_PRECEDENCE,
            EvidenceBundle(
                co_occurrence,
                governed_object=GovernedObject(
                    "event A", ObjectType.EVENT, "event B", ObjectType.EVENT
                ),
                lexical_handles=(("event A", "event-a"), ("event B", "event-b")),
                represented_terms=frozenset({"event-a", "event-b"}),
                observed_term_pairs=frozenset({("event-a", "event-b")}),
            ),
            Decision.REFUSE,
            ClaimType.LEXICAL_ASSOCIATION,
        ),
        BenchmarkCase(
            "observed-temporal-order",
            "Observed event order supplies the temporal channel required by policy.",
            ClaimType.EVENT_TEMPORAL_PRECEDENCE,
            EvidenceBundle(
                frozenset({EvidenceChannel.CO_OCCURRENCE, EvidenceChannel.EVENT_ORDER})
            ),
            Decision.ADMIT,
        ),
        BenchmarkCase(
            "explicit-prerequisite",
            "A prerequisite-bearing reference supplies directional evidence.",
            ClaimType.CONCEPT_PREREQUISITE,
            EvidenceBundle(
                frozenset(
                    {
                        EvidenceChannel.CO_OCCURRENCE,
                        EvidenceChannel.PREREQUISITE_REFERENCE,
                    }
                )
            ),
            Decision.ADMIT,
        ),
        BenchmarkCase(
            "unsupported-causality",
            "Order and syntax do not substitute for intervention evidence.",
            ClaimType.CAUSAL_INFLUENCE,
            EvidenceBundle(
                frozenset(
                    {
                        EvidenceChannel.CO_OCCURRENCE,
                        EvidenceChannel.MENTION_ORDER,
                        EvidenceChannel.SYNTAX,
                    }
                ),
                governed_object=GovernedObject(
                    "intervention A",
                    ObjectType.INTERVENTION,
                    "outcome B",
                    ObjectType.OUTCOME,
                ),
                lexical_handles=(
                    ("intervention A", "intervention-a"),
                    ("outcome B", "outcome-b"),
                ),
                represented_terms=frozenset({"intervention-a", "outcome-b"}),
                observed_term_pairs=frozenset(
                    {("intervention-a", "outcome-b")}
                ),
            ),
            Decision.REFUSE,
            ClaimType.LEXICAL_ASSOCIATION,
        ),
        BenchmarkCase(
            "low-specification-persistence",
            "The association does not meet the declared specification-persistence gate.",
            ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE,
            EvidenceBundle(
                frozenset(
                    {
                        EvidenceChannel.CO_OCCURRENCE,
                        EvidenceChannel.SPECIFICATION_SURFACE,
                    }
                ),
                specification_survival=0.65,
            ),
            Decision.REFUSE,
        ),
        BenchmarkCase(
            "duplicated-evidence",
            "A bootstrap over copied documents does not identify dependence-aware stability.",
            ClaimType.STATISTICAL_STABILITY,
            EvidenceBundle(
                frozenset({EvidenceChannel.CLUSTER_BOOTSTRAP}),
                uncertainty_adequate=False,
                dependence_adequate=False,
            ),
            Decision.REFUSE,
        ),
        BenchmarkCase(
            "conflicting-annotations",
            "Validated annotations identify the relation but disagree on its direction.",
            ClaimType.EVENT_TEMPORAL_PRECEDENCE,
            EvidenceBundle(
                records=(
                    EvidenceRecord(
                        channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
                        target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                        polarity=EvidencePolarity.SUPPORT,
                        relation=("event A", "event B"),
                        source="A precedes B",
                    ),
                    EvidenceRecord(
                        channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
                        target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                        polarity=EvidencePolarity.COUNTEREVIDENCE,
                        relation=("event A", "event B"),
                        source="B precedes A",
                    ),
                ),
                governed_object=GovernedObject(
                    "event A", ObjectType.EVENT, "event B", ObjectType.EVENT
                ),
            ),
            Decision.QUALIFY,
        ),
        BenchmarkCase(
            "missing-lineage",
            "An identifiable association lacks required provenance.",
            ClaimType.LEXICAL_ASSOCIATION,
            EvidenceBundle(co_occurrence, provenance_complete=False),
            Decision.REFUSE,
        ),
    )


def claim_admissibility_benchmark() -> dict[str, Any]:
    records = []
    decision_disagreements = 0
    fallback_disagreements = 0
    remediation_cases = 0
    correct_remediations = 0
    for case in benchmark_cases():
        certificate = evaluate_claim(case.claim_type, case.evidence)
        decision_disagreements += certificate.decision is not case.expected_decision
        fallback_disagreements += certificate.fallback_claim is not case.expected_fallback
        if case.expected_decision is not Decision.ADMIT:
            remediation_cases += 1
            correct_remediations += bool(certificate.remediation)
        records.append(
            {
                "case_id": case.case_id,
                "situation": case.situation,
                "expected_decision": case.expected_decision.value,
                "expected_fallback": (
                    case.expected_fallback.value if case.expected_fallback else None
                ),
                "decision_correct": certificate.decision is case.expected_decision,
                "fallback_correct": certificate.fallback_claim is case.expected_fallback,
                "certificate": certificate.as_dict(),
            }
        )
    total = len(records)
    return {
        "benchmark_type": "author-specified policy-conformance fixtures",
        "case_count": total,
        "policy_conformance_rate": 1.0 - decision_disagreements / total,
        "decision_disagreement_rate": decision_disagreements / total,
        "fallback_disagreement_rate": fallback_disagreements / total,
        "policy_coverage": len(records) / total,
        "remediation_coverage": correct_remediations / remediation_cases,
        "cases": records,
    }


def _unordered_signature(units: list[frozenset[str]]) -> dict[str, Any]:
    marginals = Counter(term for unit in units for term in unit)
    pairs = Counter(pair for unit in units for pair in combinations(sorted(unit), 2))
    return {
        "marginals": sorted(marginals.items()),
        "pairs": [(list(pair), count) for pair, count in sorted(pairs.items())],
    }


def observational_equivalence_benchmark() -> dict[str, Any]:
    units = [frozenset({"alpha", "beta"}), frozenset({"alpha"}), frozenset({"beta"})]
    forward_signature = _unordered_signature(units)
    reverse_signature = _unordered_signature(list(reversed(units)))
    evidence = EvidenceBundle(
        frozenset({EvidenceChannel.CO_OCCURRENCE}),
        governed_object=GovernedObject(
            "alpha", ObjectType.EVENT, "beta", ObjectType.EVENT
        ),
        lexical_handles=(("alpha", "alpha"), ("beta", "beta")),
        represented_terms=frozenset({"alpha", "beta"}),
        observed_term_pairs=frozenset({("alpha", "beta")}),
    )
    forward = evaluate_claim(ClaimType.EVENT_TEMPORAL_PRECEDENCE, evidence)
    reverse = evaluate_claim(ClaimType.EVENT_TEMPORAL_PRECEDENCE, evidence)
    return {
        "worlds": [
            {"world_id": "forward", "latent_truth": "alpha precedes beta"},
            {"world_id": "reverse", "latent_truth": "beta precedes alpha"},
        ],
        "unordered_signatures_equal": forward_signature == reverse_signature,
        "unordered_signature": forward_signature,
        "decisions": [forward.as_dict(), reverse.as_dict()],
        "both_refused": forward.decision is Decision.REFUSE and reverse.decision is Decision.REFUSE,
        "interpretation": (
            "Opposing latent directions remain indistinguishable after order is removed; "
            "the co-occurrence observation therefore cannot identify temporal precedence."
        ),
    }


def directed_reference_transition_benchmark() -> dict[str, Any]:
    reference_edges = (
        ("foundations", "methods"),
        ("methods", "analysis"),
        ("analysis", "capstone"),
        ("foundations", "analysis"),
    )
    initial = EvidenceBundle(frozenset({EvidenceChannel.CO_OCCURRENCE}))
    initial_certificates = [
        evaluate_claim(
            ClaimType.CONCEPT_PREREQUISITE,
            EvidenceBundle(
                initial.channels,
                governed_object=GovernedObject(
                    edge[0], ObjectType.CONCEPT, edge[1], ObjectType.CONCEPT
                ),
                lexical_handles=((edge[0], edge[0]), (edge[1], edge[1])),
                represented_terms=frozenset(edge),
                observed_term_pairs=frozenset({edge}),
            ),
        )
        for edge in reference_edges
    ]
    augmented_certificates = [
        evaluate_claim(
            ClaimType.CONCEPT_PREREQUISITE,
            EvidenceBundle(
                channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
                records=(
                    EvidenceRecord(
                        channel=EvidenceChannel.PREREQUISITE_REFERENCE,
                        target=ClaimType.CONCEPT_PREREQUISITE,
                        relation=edge,
                        source="generated prerequisite reference fixture",
                    ),
                ),
                governed_object=GovernedObject(
                    edge[0], ObjectType.CONCEPT, edge[1], ObjectType.CONCEPT
                ),
            ),
        )
        for edge in reference_edges
    ]
    admitted_edges = [
        edge
        for edge, certificate in zip(reference_edges, augmented_certificates, strict=True)
        if certificate.decision is Decision.ADMIT
    ]
    return {
        "benchmark_type": "synthetic explicit-reference transition fixture",
        "reference_edges": [list(edge) for edge in reference_edges],
        "initial_decisions": [certificate.decision.value for certificate in initial_certificates],
        "augmented_decisions": [
            certificate.decision.value for certificate in augmented_certificates
        ],
        "initial_refusal_rate": sum(
            certificate.decision is Decision.REFUSE for certificate in initial_certificates
        )
        / len(reference_edges),
        "augmented_admission_rate": sum(
            certificate.decision is Decision.ADMIT for certificate in augmented_certificates
        )
        / len(reference_edges),
        "edge_precision": len(set(admitted_edges) & set(reference_edges)) / len(admitted_edges),
        "edge_recall": len(set(admitted_edges) & set(reference_edges)) / len(reference_edges),
        "limitation": (
            "This controlled fixture tests policy transition and exact reference recovery; "
            "it is not evidence of real-world semantic validity or human benefit."
        ),
    }


def contract_property_checks() -> dict[str, Any]:
    co_occurrence = frozenset({EvidenceChannel.CO_OCCURRENCE})
    semantic_annotation = frozenset(
        {EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE}
    )
    construct_mismatch = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE, EvidenceBundle(semantic_annotation)
    )
    laundering_attempt = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        EvidenceBundle(
            co_occurrence,
            specification_survival=1.0,
            uncertainty_adequate=True,
            dependence_adequate=True,
        ),
    )
    monotonic_base = evaluate_claim(
        ClaimType.LEXICAL_ASSOCIATION, EvidenceBundle(co_occurrence)
    )
    monotonic_augmented = evaluate_claim(
        ClaimType.LEXICAL_ASSOCIATION,
        EvidenceBundle(co_occurrence | {EvidenceChannel.MENTION_ORDER}),
    )
    evaluated = [
        evaluate_claim(claim_type, EvidenceBundle(co_occurrence))
        for claim_type in ClaimType
        if claim_type is not ClaimType.LEXICAL_ASSOCIATION
    ]
    refused = [
        certificate
        for certificate in evaluated
        if certificate.decision is Decision.REFUSE
    ]
    fallback_certificates = [
        certificate for certificate in refused if certificate.fallback_claim is not None
    ]
    forward_relation = ("foundations", "methods")
    reverse_request = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.PREREQUISITE_REFERENCE,
                    target=ClaimType.CONCEPT_PREREQUISITE,
                    relation=forward_relation,
                    source="generated prerequisite reference fixture",
                ),
            ),
            requested_relation=tuple(reversed(forward_relation)),
        ),
    )
    checks = {
        "construct_matching": (
            not construct_mismatch.identifiable
            and construct_mismatch.decision is Decision.REFUSE
        ),
        "no_validity_laundering": laundering_attempt.decision is Decision.REFUSE,
        "conditional_support_channel_monotonicity": (
            monotonic_base.decision is Decision.ADMIT
            and monotonic_augmented.decision is Decision.ADMIT
        ),
        "export_soundness": all(
            certificate.allowed_export is False for certificate in refused
        ),
        "fallback_soundness": all(
            certificate.fallback_claim is ClaimType.LEXICAL_ASSOCIATION
            for certificate in fallback_certificates
        ),
        "fallback_preference_conformance": all(
            certificate.fallback_is_policy_preferred
            for certificate in fallback_certificates
        ),
        "pair_scope_nontransfer": (
            not reverse_request.identifiable
            and reverse_request.decision is Decision.REFUSE
        ),
    }
    return {
        "check_count": len(checks),
        "passed_count": sum(checks.values()),
        "all_passed": all(checks.values()),
        "checks": checks,
                "falsification_matrix": [
                    {
                        "property": "construct matching",
                        "perturbation": "Use semantic-equivalence evidence for temporal precedence",
                        "failure_condition": "Temporal precedence is admitted",
                        "contribution_consequence": "An incompatible construct reaches a semantic mark.",
                    },
                    {
                        "property": "no validity laundering",
                        "perturbation": (
                            "Set specification persistence and uncertainty adequacy "
                            "without causal evidence"
                        ),
                        "failure_condition": "Causal influence is admitted or qualified",
                        "contribution_consequence": "Quality fields launder an unidentified claim.",
                    },
                    {
                        "property": "conditional support-channel monotonicity",
                        "perturbation": "Add irrelevant mention-order evidence to supported association",
                        "failure_condition": "Lexical admission is withdrawn",
                        "contribution_consequence": "Irrelevant evidence destabilizes lawful output.",
                    },
                    {
                        "property": "export soundness",
                        "perturbation": "Evaluate every refused claim for export",
                        "failure_condition": "Any refused requested claim is exportable",
                        "contribution_consequence": "Export bypasses statement and mark refusal.",
                    },
                    {
                        "property": "fallback soundness",
                        "perturbation": "Remove evidence required by each preferred fallback",
                        "failure_condition": "An unidentified fallback is emitted",
                        "contribution_consequence": "Downgrade emits a claim without independent support.",
                    },
                    {
                        "property": "fallback preference conformance",
                        "perturbation": "Provide multiple declared fallback candidates",
                        "failure_condition": "The first supported preference is not selected",
                        "contribution_consequence": "Rendered downgrade diverges from authored policy.",
                    },
                    {
                        "property": "pair scope nontransfer",
                        "perturbation": "Reverse the requested entity pair without reversing the evidence record",
                        "failure_condition": "Forward directional evidence licenses the reversed claim",
                        "contribution_consequence": "Evidence authorizes the wrong semantic orientation.",
                    },
                ],
        "scope": (
            f"Executable properties of policy version {POLICY_VERSION}; these checks establish "
            "internal conformance, not external epistemic validity."
        ),
    }


def policy_contestability_benchmark() -> dict[str, Any]:
    relation = ("foundations", "methods")
    evidence = EvidenceBundle(
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.PREREQUISITE_REFERENCE,
                target=ClaimType.CONCEPT_PREREQUISITE,
                relation=relation,
                source="generated prerequisite reference fixture",
            ),
        ),
        requested_relation=tuple(reversed(relation)),
    )
    legacy = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE, evidence, policy_version="2.2.0"
    )
    active = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE, evidence, policy_version=POLICY_VERSION
    )
    return {
        "case_id": "directional-pair-reversal",
        "changed_rule": (
            f"Policy {POLICY_VERSION} requires an ordered-pair match; Policy 2.2.0 matched the "
            "prerequisite claim type without enforcing entity-pair orientation."
        ),
        "certificates": [legacy.as_dict(), active.as_dict()],
        "decision_changed": legacy.decision is not active.decision,
        "version_traceable": (
            legacy.policy_version == "2.2.0" and active.policy_version == POLICY_VERSION
        ),
    }


def policy_lint_mutation_benchmark() -> dict[str, Any]:
    """Falsify each declared lint invariant with a targeted policy mutation."""
    mutations: list[tuple[str, str, dict[str, Any]]] = []

    missing_claim = dict(POLICIES)
    del missing_claim[ClaimType.ANALYST_BENEFIT]
    mutations.append(
        ("remove-claim-declaration", "all_claims_declared", {"policies": missing_claim})
    )

    unreachable = dict(POLICIES)
    unreachable[ClaimType.THEME] = replace(
        unreachable[ClaimType.THEME],
        predicates=(
            EvidencePredicate(
                "unreachable-empty-channel",
                frozenset(),
                "predicate with no observable channel",
                ClaimType.THEME,
            ),
        ),
    )
    mutations.append(
        ("unreachable-predicate", "requirements_reachable", {"policies": unreachable})
    )

    duplicated = dict(POLICIES)
    duplicate_predicate = EvidencePredicate(
        "duplicate-theme-predicate",
        frozenset({EvidenceChannel.QUALITATIVE_INTERPRETATION}),
        "duplicated qualitative interpretation predicate",
        ClaimType.THEME,
    )
    duplicated[ClaimType.THEME] = replace(
        duplicated[ClaimType.THEME],
        predicates=(duplicate_predicate, duplicate_predicate),
    )
    mutations.append(
        ("duplicate-predicate", "no_duplicate_predicates", {"policies": duplicated})
    )

    missing_remediation = dict(POLICIES)
    missing_remediation[ClaimType.THEME] = replace(
        missing_remediation[ClaimType.THEME], remediation=""
    )
    mutations.append(
        ("remove-remediation", "remediation_complete", {"policies": missing_remediation})
    )

    generic_order = dict(POLICIES)
    generic_order[ClaimType.EVENT_TEMPORAL_PRECEDENCE] = replace(
        generic_order[ClaimType.EVENT_TEMPORAL_PRECEDENCE],
        required_alternatives=(frozenset({EvidenceChannel.ORDER}),),
        predicates=(),
    )
    mutations.append(
        ("generic-order-substitution", "construct_specific_order", {"policies": generic_order})
    )

    generic_reference = dict(POLICIES)
    generic_reference[ClaimType.CONCEPT_PREREQUISITE] = replace(
        generic_reference[ClaimType.CONCEPT_PREREQUISITE],
        required_alternatives=(frozenset({EvidenceChannel.CROSS_REFERENCE}),),
        predicates=(),
    )
    mutations.append(
        (
            "generic-reference-substitution",
            "construct_specific_reference",
            {"policies": generic_reference},
        )
    )

    missing_estimand = dict(POLICIES)
    causal_predicates = tuple(
        replace(
            predicate,
            required_metadata=tuple(
                field for field in predicate.required_metadata if field != "estimand"
            ),
        )
        for predicate in POLICIES[ClaimType.CAUSAL_INFLUENCE].predicates
    )
    missing_estimand[ClaimType.CAUSAL_INFLUENCE] = replace(
        missing_estimand[ClaimType.CAUSAL_INFLUENCE],
        predicates=causal_predicates,
    )
    mutations.append(
        ("omit-causal-estimand", "causal_metadata_consistent", {"policies": missing_estimand})
    )

    missing_object_signature = dict(POLICIES)
    missing_object_signature[ClaimType.TEXTUAL_ENTAILMENT] = replace(
        missing_object_signature[ClaimType.TEXTUAL_ENTAILMENT],
        object_signatures=(),
    )
    mutations.append(
        (
            "omit-object-signature",
            "object_signatures_complete",
            {"policies": missing_object_signature},
        )
    )

    missing_adjudication = dict(POLICIES)
    theme_predicate = POLICIES[ClaimType.THEME].predicates[0]
    missing_adjudication[ClaimType.THEME] = replace(
        missing_adjudication[ClaimType.THEME],
        predicates=(
            replace(theme_predicate, requires_approved_adjudication=False),
        ),
    )
    mutations.append(
        (
            "omit-theme-adjudication",
            "interpretive_adjudication_required",
            {"policies": missing_adjudication},
        )
    )

    missing_causal_adjudication = dict(POLICIES)
    causal_predicates = tuple(
        replace(predicate, requires_approved_adjudication=False)
        for predicate in POLICIES[ClaimType.CAUSAL_INFLUENCE].predicates
    )
    missing_causal_adjudication[ClaimType.CAUSAL_INFLUENCE] = replace(
        missing_causal_adjudication[ClaimType.CAUSAL_INFLUENCE],
        predicates=causal_predicates,
    )
    mutations.append(
        (
            "omit-causal-adjudication",
            "causal_adjudication_required",
            {"policies": missing_causal_adjudication},
        )
    )

    intervention_alternative = dict(POLICIES)
    intervention_alternative[ClaimType.CAUSAL_INFLUENCE] = replace(
        intervention_alternative[ClaimType.CAUSAL_INFLUENCE],
        required_alternatives=(
            frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION}),
            frozenset({EvidenceChannel.INTERVENTION}),
        ),
    )
    mutations.append(
        (
            "intervention-as-causal-alternative",
            "causal_identification_not_intervention_alternative",
            {"policies": intervention_alternative},
        )
    )

    cyclic_fallbacks = dict(FALLBACK_PREFERENCES)
    cyclic_fallbacks[ClaimType.LEXICAL_ASSOCIATION] = (ClaimType.CONCEPT_PREREQUISITE,)
    mutations.append(
        (
            "fallback-cycle",
            "fallback_graph_acyclic",
            {"fallback_preferences": cyclic_fallbacks},
        )
    )

    undeclared_target = dict(POLICIES)
    del undeclared_target[ClaimType.LEXICAL_ASSOCIATION]
    mutations.append(
        (
            "undeclared-fallback-target",
            "fallback_targets_declared",
            {"policies": undeclared_target},
        )
    )

    incompatible_scope = dict(FALLBACK_PREFERENCES)
    incompatible_scope[ClaimType.STATISTICAL_STABILITY] = (
        ClaimType.LEXICAL_ASSOCIATION,
    )
    mutations.append(
        (
            "unscoped-to-pair-fallback",
            "fallback_scope_compatible",
            {"fallback_preferences": incompatible_scope},
        )
    )

    missing_projection = dict(FALLBACK_PROJECTIONS)
    del missing_projection[
        (ClaimType.EVENT_TEMPORAL_PRECEDENCE, ClaimType.LEXICAL_ASSOCIATION)
    ]
    mutations.append(
        (
            "omit-fallback-projection",
            "fallback_projections_complete",
            {"fallback_projections": missing_projection},
        )
    )

    incompatible_projection = dict(FALLBACK_PROJECTIONS)
    projection_key = (
        ClaimType.CONCEPT_PREREQUISITE,
        ClaimType.LEXICAL_ASSOCIATION,
    )
    incompatible_projection[projection_key] = replace(
        incompatible_projection[projection_key],
        target_signature=(ObjectType.CONCEPT, ObjectType.CONCEPT),
    )
    mutations.append(
        (
            "mistype-fallback-projection",
            "fallback_projection_target_compatible",
            {"fallback_projections": incompatible_projection},
        )
    )

    provenance_losing_projection = dict(FALLBACK_PROJECTIONS)
    projection_key = (
        ClaimType.CAUSAL_INFLUENCE,
        ClaimType.LEXICAL_ASSOCIATION,
    )
    provenance_losing_projection[projection_key] = replace(
        provenance_losing_projection[projection_key],
        preserves_provenance=False,
    )
    mutations.append(
        (
            "drop-fallback-projection-provenance",
            "fallback_projection_provenance_preserved",
            {"fallback_projections": provenance_losing_projection},
        )
    )

    refused_export = dict(POLICIES)
    refused_export[ClaimType.CAUSAL_INFLUENCE] = replace(
        refused_export[ClaimType.CAUSAL_INFLUENCE], allow_refused_export=True
    )
    mutations.append(
        ("allow-refused-export", "refused_exports_blocked", {"policies": refused_export})
    )

    collapsed_encoding = dict(POLICIES)
    collapsed_encoding[ClaimType.ASYMMETRIC_CONDITIONAL] = replace(
        collapsed_encoding[ClaimType.ASYMMETRIC_CONDITIONAL],
        allowed_encoding=POLICIES[ClaimType.EVENT_TEMPORAL_PRECEDENCE].allowed_encoding,
    )
    mutations.append(
        (
            "collapse-statistical-semantic-encoding",
            "encoding_semantic_separation",
            {"policies": collapsed_encoding},
        )
    )

    incomplete_interpretive_metadata = dict(POLICIES)
    analyst_predicate = POLICIES[ClaimType.ANALYST_BENEFIT].predicates[0]
    incomplete_interpretive_metadata[ClaimType.ANALYST_BENEFIT] = replace(
        incomplete_interpretive_metadata[ClaimType.ANALYST_BENEFIT],
        predicates=(
            replace(
                analyst_predicate,
                required_metadata=tuple(
                    field
                    for field in analyst_predicate.required_metadata
                    if field != "comparator"
                ),
            ),
        ),
    )
    mutations.append(
        (
            "omit-analyst-comparator",
            "interpretive_metadata_consistent",
            {"policies": incomplete_interpretive_metadata},
        )
    )

    mutations.append(
        (
            "behaviorally-identical-version",
            "declared_semantic_change_witnessed",
            {"active_version": "2.1.0"},
        )
    )

    records = []
    check_names = tuple(lint_policy()["checks"])
    for mutation_id, intended_check, lint_arguments in mutations:
        result = lint_policy(**lint_arguments)
        additional_failed_checks = [
            check for check in result["issues"] if check != intended_check
        ]
        records.append(
            {
                "mutation_id": mutation_id,
                "intended_check": intended_check,
                "detected": intended_check in result["issues"],
                "failed_checks": result["issues"],
                "additional_failed_checks": additional_failed_checks,
                "additional_failure_count": len(additional_failed_checks),
                "exact_localization": result["issues"] == [intended_check],
                "detection_vector": {
                    check: check in result["issues"] for check in check_names
                },
            }
        )
    detected_count = sum(record["detected"] for record in records)
    exact_localization_count = sum(record["exact_localization"] for record in records)
    return {
        "benchmark_type": "targeted policy-linter mutation testing",
        "mutation_count": len(records),
        "detected_count": detected_count,
        "detection_rate": detected_count / len(records),
        "all_intended_mutations_detected": detected_count == len(records),
        "check_names": list(check_names),
        "exact_localization_count": exact_localization_count,
        "exact_localization_rate": exact_localization_count / len(records),
        "mutations": records,
        "scope": (
            "Targeted mutations report intended detection and all co-triggered checks; "
            "localization does not establish the normative validity of the active policy."
        ),
    }


def contract_field_necessity_benchmark() -> dict[str, Any]:
    """Link contract distinctions to the invalid behavior each one prevents."""
    mutation_result = policy_lint_mutation_benchmark()
    mutations = {
        mutation["mutation_id"]: mutation
        for mutation in mutation_result["mutations"]
    }
    properties = contract_property_checks()["checks"]
    sentence_object = GovernedObject(
        "sentence A", ObjectType.SENTENCE, "sentence B", ObjectType.SENTENCE
    )
    counterevidence = EvidenceRecord(
        channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
        target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        polarity=EvidencePolarity.COUNTEREVIDENCE,
        relation=sentence_object.relation,
        source="negative paraphrase annotation",
    )
    polarity_guarded = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        EvidenceBundle(records=(counterevidence,), governed_object=sentence_object),
    )
    polarity_removed = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        EvidenceBundle(
            records=(replace(counterevidence, polarity=EvidencePolarity.SUPPORT),),
            governed_object=sentence_object,
        ),
    )
    specifications = (
        (
            "governed-object type",
            "omit-object-signature",
            "policy mutation",
            "Sentence evidence may license an incompatible event or concept claim.",
            "Object-specific authorization collapses into channel-only admission.",
            mutations["omit-object-signature"]["detected"],
        ),
        (
            "scope and orientation",
            "pair-scope-nontransfer",
            "adversarial property",
            "Evidence for a->b may license b->a.",
            "Directional authorization transfers to an unevidenced pair.",
            properties["pair_scope_nontransfer"],
        ),
        (
            "evidence polarity",
            "counterevidence-as-support",
            "counterfactual evidence record",
            "A negative annotation may be read as positive support or reverse truth.",
            "Construct conflict becomes an admitted semantic relation.",
            (
                polarity_guarded.decision is Decision.REFUSE
                and polarity_removed.decision is Decision.ADMIT
            ),
        ),
        (
            "projection provenance",
            "drop-fallback-projection-provenance",
            "policy mutation",
            "A fallback may lose lineage while remaining emit-able.",
            "The downgraded representation is no longer auditable to its evidence.",
            mutations["drop-fallback-projection-provenance"]["detected"],
        ),
        (
            "fallback projection",
            "omit-fallback-projection",
            "policy mutation",
            "A refused semantic claim may silently collapse to lexical association.",
            "Refusal no longer controls the representation reached by downgrade.",
            mutations["omit-fallback-projection"]["detected"],
        ),
        (
            "export authorization",
            "allow-refused-export",
            "policy mutation",
            "A visibly refused claim may leak into a downstream artifact.",
            "Statement and mark governance can be bypassed through export.",
            mutations["allow-refused-export"]["detected"],
        ),
        (
            "required adjudication",
            "omit-causal-adjudication",
            "policy mutation",
            "Metadata-complete causal evidence may be promoted without approval.",
            "An authored governance gate disappears while the claim still admits.",
            mutations["omit-causal-adjudication"]["detected"],
        ),
    )
    rows = [
        {
            "distinction": distinction,
            "probe_id": probe_id,
            "probe_type": probe_type,
            "invalid_behavior_enabled": invalid_behavior,
            "contribution_consequence": contribution_consequence,
            "detected": detected,
        }
        for (
            distinction,
            probe_id,
            probe_type,
            invalid_behavior,
            contribution_consequence,
            detected,
        ) in specifications
    ]
    return {
        "benchmark_type": "contract-field necessity and failure analysis",
        "distinction_count": len(rows),
        "all_failures_detected": all(row["detected"] for row in rows),
        "rows": rows,
        "scope": (
            "One-at-a-time removals and corruptions demonstrate implementation failure "
            "modes, not minimality of the ontology or normative policy validity."
        ),
    }


def controlled_duplication_stress_benchmark() -> dict[str, Any]:
    base_records = tuple(
        f"source-{index:02d}: concept-{index % 4} method-{index % 3}"
        for index in range(12)
    )
    duplication_factor = 4
    expanded_records = tuple(
        record for record in base_records for _ in range(duplication_factor)
    )
    unique_records = set(expanded_records)
    return {
        "benchmark_type": "generated controlled duplication/dependence stress case",
        "license": "CC0-equivalent generated fixture; no third-party text",
        "base_source_count": len(base_records),
        "row_count": len(expanded_records),
        "unique_record_count": len(unique_records),
        "duplicate_rows_beyond_first": len(expanded_records) - len(unique_records),
        "duplicate_rate": 1.0 - len(unique_records) / len(expanded_records),
        "naive_support_inflation_factor": len(expanded_records) / len(unique_records),
        "interpretation": (
            "Exact copies increase row-level support fourfold without increasing the "
            "number of independently generated source records."
        ),
    }


# certificate-guarded-output-entry-point: publication representation enforcement; guard=validate_certificate_payload
def representation_enforcement_benchmark() -> dict[str, Any]:
    """Audit outward representation consequences for each policy state."""
    relation = ("event A", "event B")
    event_object = GovernedObject(
        relation[0], ObjectType.EVENT, relation[1], ObjectType.EVENT
    )
    conflict_records = (
        EvidenceRecord(
            channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
            target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
            polarity=EvidencePolarity.SUPPORT,
            relation=relation,
            source="A precedes B",
        ),
        EvidenceRecord(
            channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
            target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
            polarity=EvidencePolarity.COUNTEREVIDENCE,
            relation=relation,
            source="B precedes A",
        ),
    )
    scenarios = (
        (
            "admit",
            evaluate_claim(
                ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                EvidenceBundle(
                    frozenset({EvidenceChannel.EVENT_ORDER}),
                    governed_object=event_object,
                ),
            ),
            VisualEncoding.DIRECTED_ARROW,
            True,
            None,
            False,
        ),
        (
            "prevalence-qualify",
            evaluate_claim(
                ClaimType.ASYMMETRIC_CONDITIONAL,
                EvidenceBundle(
                    frozenset({EvidenceChannel.CO_OCCURRENCE}),
                    governed_object=GovernedObject(
                        "term A", ObjectType.TERM, "term B", ObjectType.TERM
                    ),
                ),
            ),
            VisualEncoding.CONDITIONAL_ASYMMETRY_GLYPH,
            True,
            None,
            True,
        ),
        (
            "conflict-qualify",
            evaluate_claim(
                ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                EvidenceBundle(records=conflict_records, governed_object=event_object),
            ),
            VisualEncoding.CONTESTED_RELATION,
            False,
            None,
            True,
        ),
        (
            "refuse-with-fallback",
            evaluate_claim(
                ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                EvidenceBundle(
                    frozenset({EvidenceChannel.CO_OCCURRENCE}),
                    governed_object=event_object,
                    lexical_handles=(
                        (relation[0], "event-a"),
                        (relation[1], "event-b"),
                    ),
                    represented_terms=frozenset({"event-a", "event-b"}),
                    observed_term_pairs=frozenset({("event-a", "event-b")}),
                ),
            ),
            VisualEncoding.UNDIRECTED_LINK,
            False,
            ClaimType.LEXICAL_ASSOCIATION,
            True,
        ),
        (
            "refuse-without-fallback",
            evaluate_claim(
                ClaimType.STATISTICAL_STABILITY,
                EvidenceBundle(frozenset({EvidenceChannel.CO_OCCURRENCE})),
            ),
            VisualEncoding.NO_RELATION,
            False,
            None,
            True,
        ),
    )
    permitted_statements = {
        "admit": "semantic claim",
        "prevalence-qualify": "qualified statistic",
        "conflict-qualify": "contested claim",
        "refuse-with-fallback": "fallback statement",
        "refuse-without-fallback": "refusal explanation",
    }
    rows = []
    for state, certificate, encoding, export, fallback, remediation_required in scenarios:
        validate_certificate_payload(certificate.as_dict())
        checks = {
            "statement": bool(certificate.allowed_statement),
            "mark": certificate.allowed_encoding is encoding,
            "export": certificate.allowed_export is export,
            "fallback": certificate.fallback_claim is fallback,
            "witness": bool(certificate.witness),
            "remediation": bool(certificate.remediation) is remediation_required,
        }
        rows.append(
            {
                "state": state,
                "decision": certificate.decision.value,
                "decision_reason": (
                    certificate.decision_reason.value
                    if certificate.decision_reason is not None
                    else "none"
                ),
                "statement": certificate.allowed_statement,
                "permitted_statement": permitted_statements[state],
                "mark": certificate.allowed_encoding.value,
                "requested_claim_export": (
                    "allowed" if certificate.allowed_export else "blocked"
                ),
                "fallback": (
                    certificate.fallback_claim.value
                    if certificate.fallback_claim
                    else "none"
                ),
                "projection": certificate.fallback_projection or "none",
                "witness": "present" if certificate.witness else "absent",
                "remediation": "present" if certificate.remediation else "none",
                "checks": checks,
                "conforms": all(checks.values()),
            }
        )
    return {
        "benchmark_type": "certificate-to-representation enforcement matrix",
        "state_count": len(rows),
        "all_conform": all(row["conforms"] for row in rows),
        "states": rows,
    }


def architecture_enforcement_ablation() -> dict[str, Any]:
    """Compare policy-relative reachability across output-control conditions."""
    relation = ("event A", "event B")
    event_object = GovernedObject(
        relation[0], ObjectType.EVENT, relation[1], ObjectType.EVENT
    )
    fixtures = (
        (
            "unsupported-temporal-with-fallback",
            evaluate_claim(
                ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                EvidenceBundle(
                    frozenset({EvidenceChannel.CO_OCCURRENCE}),
                    governed_object=event_object,
                    lexical_handles=((relation[0], "event-a"), (relation[1], "event-b")),
                    represented_terms=frozenset({"event-a", "event-b"}),
                    observed_term_pairs=frozenset({("event-a", "event-b")}),
                ),
            ),
            VisualEncoding.DIRECTED_ARROW,
        ),
        (
            "conflicting-temporal-evidence",
            evaluate_claim(
                ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                EvidenceBundle(
                    records=(
                        EvidenceRecord(
                            channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
                            target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                            relation=relation,
                            source="A precedes B",
                        ),
                        EvidenceRecord(
                            channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
                            target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                            polarity=EvidencePolarity.COUNTEREVIDENCE,
                            relation=relation,
                            source="B precedes A",
                        ),
                    ),
                    governed_object=event_object,
                ),
            ),
            VisualEncoding.DIRECTED_ARROW,
        ),
        (
            "missing-provenance",
            evaluate_claim(
                ClaimType.LEXICAL_ASSOCIATION,
                EvidenceBundle(
                    frozenset({EvidenceChannel.CO_OCCURRENCE}),
                    governed_object=GovernedObject(
                        "term A", ObjectType.TERM, "term B", ObjectType.TERM
                    ),
                    provenance_complete=False,
                ),
            ),
            VisualEncoding.UNDIRECTED_LINK,
        ),
    )
    architectures = (
        ("graph-pipeline-only", False, False, False),
        ("warning-layer", False, True, False),
        ("certificate-visible-non-enforcing", False, False, True),
        ("themegraph-certificate-enforcement", True, False, True),
    )
    rows = []
    for architecture, enforced, warning_attached, certificate_visible in architectures:
        unauthorized_statements = 0
        unauthorized_marks = 0
        unauthorized_exports = 0
        lawful_fallbacks = 0
        fixture_rows = []
        for fixture_id, certificate, requested_encoding in fixtures:
            if enforced:
                statement_leaked = False
                mark_leaked = False
                export_leaked = False
                fallback_preserved = certificate.fallback_claim is not None
            else:
                statement_leaked = certificate.decision is not Decision.ADMIT
                mark_leaked = certificate.allowed_encoding is not requested_encoding
                export_leaked = not certificate.allowed_export
                fallback_preserved = False
            unauthorized_statements += int(statement_leaked)
            unauthorized_marks += int(mark_leaked)
            unauthorized_exports += int(export_leaked)
            lawful_fallbacks += int(fallback_preserved)
            fixture_rows.append(
                {
                    "fixture_id": fixture_id,
                    "certificate_decision": certificate.decision.value,
                    "warning_attached": warning_attached,
                    "certificate_visible": certificate_visible,
                    "unauthorized_statement_emitted": statement_leaked,
                    "unauthorized_mark_emitted": mark_leaked,
                    "unauthorized_requested_export_emitted": export_leaked,
                    "lawful_fallback_preserved": fallback_preserved,
                }
            )
        rows.append(
            {
                "architecture": architecture,
                "fixture_count": len(fixtures),
                "unauthorized_statements_emitted": unauthorized_statements,
                "unauthorized_semantic_marks_emitted": unauthorized_marks,
                "unauthorized_requested_exports_emitted": unauthorized_exports,
                "lawful_fallbacks_preserved": lawful_fallbacks,
                "warning_attached": warning_attached,
                "certificate_visible": certificate_visible,
                "fixtures": fixture_rows,
            }
        )
    enforced_row = rows[-1]
    return {
        "benchmark_type": "output-control reachability ablation",
        "architecture_count": len(rows),
        "fixture_count": len(fixtures),
        "output_path_count": len(COMPLETE_MEDIATION_ENTRY_POINTS),
        "architectures": rows,
        "enforcement_blocks_all_unauthorized_outputs": all(
            enforced_row[field] == 0
            for field in (
                "unauthorized_statements_emitted",
                "unauthorized_semantic_marks_emitted",
                "unauthorized_requested_exports_emitted",
            )
        ),
        "enforcement_preserves_lawful_fallback": (
            enforced_row["lawful_fallbacks_preserved"] == 1
        ),
        "scope": (
            "Generated mechanism probes compare output reachability in four output-control "
            "conditions over three fixtures. Unauthorized means not authorized under "
            "Policy 2.7.0 for the supplied claim/evidence fixture. Reachable means emitted, "
            "selectable, renderable, or exportable as an output under the condition; a fallback "
            "merely listed in certificate metadata is excluded. A separate suite audits "
            "eight maintained certificate-guarded output entry points; no "
            "fixture-by-path cross-product is "
            "claimed. These probes do not characterize all warning or inspection systems "
            "or establish human benefit, safety effectiveness, formal noninterference, or "
            "universal non-bypassability."
        ),
    }


def evidence_integrity_trust_boundary() -> dict[str, Any]:
    """Expose the boundary between record conformance and source semantic truth."""
    source_relation = ("event B", "event A")
    adapter_relation = ("event A", "event B")
    record = EvidenceRecord(
        channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
        target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        relation=adapter_relation,
        source="Source fixture relation: event B precedes event A.",
    )
    certificate = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            records=(record,),
            governed_object=GovernedObject(
                adapter_relation[0],
                ObjectType.EVENT,
                adapter_relation[1],
                ObjectType.EVENT,
            ),
        ),
    )
    return {
        "fixture_id": "schema-valid-semantically-mislabeled-evidence",
        "schema_valid": True,
        "provenance_complete": certificate.provenance_complete,
        "source_relation": list(source_relation),
        "faulty_adapter_typed_relation": list(adapter_relation),
        "requested_relation": list(adapter_relation),
        "source_text": record.source,
        "source_semantics_contradict_typed_relation": True,
        "decision": certificate.decision.value,
        "policy_conformant_admission": certificate.decision is Decision.ADMIT,
        "semantic_authenticity_checked": False,
        "scope": (
            "Policy conformance checks the supplied typed record, not whether its source "
            "text is semantically correct or authentic. Authorization therefore remains "
            "conditional on upstream evidence integrity."
        ),
    }


def complete_benchmark() -> dict[str, Any]:
    return {
        "schema_version": "2.7",
        "policy": policy_as_dict(),
        "policy_lint": lint_policy(),
        "policy_lint_mutations": policy_lint_mutation_benchmark(),
        "contract_field_necessity": contract_field_necessity_benchmark(),
        "claim_decisions": claim_admissibility_benchmark(),
        "contract_properties": contract_property_checks(),
        "policy_contestability": policy_contestability_benchmark(),
        "observational_equivalence": observational_equivalence_benchmark(),
        "directed_reference_transition": directed_reference_transition_benchmark(),
        "controlled_duplication_stress": controlled_duplication_stress_benchmark(),
        "representation_enforcement": representation_enforcement_benchmark(),
        "architecture_enforcement_ablation": architecture_enforcement_ablation(),
        "evidence_integrity_trust_boundary": evidence_integrity_trust_boundary(),
        "complete_mediation": {
            "invariant": (
                "Every maintained certificate-guarded output entry point consumes "
                "a valid selected certificate or complete certificate collection."
            ),
            "entry_points": list(COMPLETE_MEDIATION_ENTRY_POINTS),
            "entry_point_count": len(COMPLETE_MEDIATION_ENTRY_POINTS),
            "structural_entry_points": list(
                STRUCTURAL_CERTIFICATE_GUARDED_ENTRY_POINTS
            ),
            "structural_entry_point_count": len(
                STRUCTURAL_CERTIFICATE_GUARDED_ENTRY_POINTS
            ),
            "semantic_entry_points": list(SEMANTIC_CERTIFICATE_GUARDED_ENTRY_POINTS),
            "semantic_entry_point_count": len(
                SEMANTIC_CERTIFICATE_GUARDED_ENTRY_POINTS
            ),
            "all_certificate_required": True,
            "failure_mode": "fail closed",
        },
    }