import inspect

import pytest

from themegraph.admissibility import (
    POLICIES,
    AdjudicationStatus,
    ClaimFamily,
    ClaimType,
    Decision,
    EvidenceBundle,
    EvidenceChannel,
    EvidencePolarity,
    EvidenceRecord,
    GovernedObject,
    ObjectType,
    ReasonCode,
    VisualEncoding,
    evaluate_claim,
    lint_policy,
    policy_as_dict,
)


def test_unidentifiable_claim_cannot_be_laundered_by_other_checks() -> None:
    certificate = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        EvidenceBundle(
            frozenset({EvidenceChannel.CO_OCCURRENCE}),
            provenance_complete=True,
            specification_survival=1.0,
            uncertainty_adequate=True,
        ),
    )

    assert certificate.decision is Decision.REFUSE
    assert certificate.fallback_claim is None
    assert certificate.allowed_encoding is VisualEncoding.NO_RELATION
    assert certificate.allowed_export is False


def test_fifteenth_claim_extends_policy_without_evaluator_branching() -> None:
    relation = ("data stewardship", "responsible data governance")
    certificate = evaluate_claim(
        ClaimType.CONCEPT_EQUIVALENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                    target=ClaimType.CONCEPT_EQUIVALENCE,
                    relation=relation,
                    source="concept-equivalence adjudication record",
                ),
            ),
            governed_object=GovernedObject(
                relation[0], ObjectType.CONCEPT, relation[1], ObjectType.CONCEPT
            ),
        ),
    )

    assert len(ClaimType) == 15
    assert "CONCEPT_EQUIVALENCE" not in inspect.getsource(evaluate_claim)
    assert certificate.decision is Decision.ADMIT
    assert certificate.allowed_encoding is VisualEncoding.UNDIRECTED_LINK
    assert certificate.allowed_export is True
    serialized = certificate.as_dict()
    assert serialized["claim_type"] == "concept-equivalence"
    assert serialized["allowed_statement"].startswith("The concept pair")
    policy_claims = {row["claim"]: row for row in policy_as_dict()["claims"]}
    assert policy_claims["concept-equivalence"]["scope_semantics"] == "symmetric"
    assert lint_policy()["all_passed"] is True


def test_incomplete_fifteenth_claim_extension_fails_policy_lint() -> None:
    incomplete = dict(POLICIES)
    incomplete.pop(ClaimType.CONCEPT_EQUIVALENCE)

    result = lint_policy(policies=incomplete)

    assert result["all_passed"] is False
    assert "all_claims_declared" in result["issues"]


def test_bound_semantic_fallback_uses_declared_lexical_projection() -> None:
    relation = ("rain started", "roads flooded")
    certificate = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            frozenset({EvidenceChannel.CO_OCCURRENCE}),
            governed_object=GovernedObject(
                relation[0], ObjectType.EVENT, relation[1], ObjectType.EVENT
            ),
            lexical_handles=((relation[0], "rain"), (relation[1], "flood")),
            represented_terms=frozenset({"rain", "flood"}),
            observed_term_pairs=frozenset({("flood", "rain")}),
        ),
    )

    assert certificate.decision is Decision.REFUSE
    assert certificate.fallback_claim is ClaimType.LEXICAL_ASSOCIATION
    assert certificate.fallback_projection == "lexicalize-pair-v1"
    assert certificate.fallback_projected_object == GovernedObject(
        "rain", ObjectType.TERM, "flood", ObjectType.TERM
    )
    assert certificate.fallback_projection_provenance == (
        (
            "Canonical lexical handles map 'rain started' to 'rain' and "
            "'roads flooded' to 'flood'."
        ),
        "Both projected handles occur in the represented corpus vocabulary.",
        "The projected pair has independently observed co-occurrence evidence.",
        "Evidence-record and corpus lineage retained from the requested claim bundle.",
    )
    assert certificate.as_dict()["fallback_projected_object"] == {
        "source": "rain",
        "source_type": "term",
        "target": "flood",
        "target_type": "term",
    }


def test_qualified_fallback_inherits_target_consequences() -> None:
    relation = ("rain started", "roads flooded")
    lexical_relation = ("rain", "flood")
    certificate = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.CO_OCCURRENCE,
                    target=ClaimType.LEXICAL_ASSOCIATION,
                    relation=lexical_relation,
                    source="lexical support",
                ),
                EvidenceRecord(
                    channel=EvidenceChannel.CO_OCCURRENCE,
                    target=ClaimType.LEXICAL_ASSOCIATION,
                    polarity=EvidencePolarity.COUNTEREVIDENCE,
                    relation=lexical_relation,
                    source="lexical counterevidence",
                ),
            ),
            governed_object=GovernedObject(
                relation[0], ObjectType.EVENT, relation[1], ObjectType.EVENT
            ),
            lexical_handles=((relation[0], "rain"), (relation[1], "flood")),
            represented_terms=frozenset(lexical_relation),
            observed_term_pairs=frozenset({lexical_relation}),
        ),
    )

    assert certificate.decision is Decision.REFUSE
    assert certificate.fallback_claim is ClaimType.LEXICAL_ASSOCIATION
    assert certificate.fallback_decision is Decision.QUALIFY
    assert certificate.allowed_statement == (
        "Construct-matched support and counterevidence contest this relation."
    )
    assert certificate.allowed_encoding is VisualEncoding.CONTESTED_RELATION
    assert certificate.fallback_allowed_export is False
    assert certificate.allowed_export is False


@pytest.mark.parametrize(
    ("lexical_handles", "represented_terms", "observed_term_pairs"),
    [
        (
            (("event A", "alpha"),),
            frozenset({"alpha", "beta"}),
            frozenset({("alpha", "beta")}),
        ),
        (
            (("event A", "alpha"), ("event B", "beta")),
            frozenset({"alpha"}),
            frozenset({("alpha", "beta")}),
        ),
        (
            (("event A", "same"), ("event B", "same")),
            frozenset({"same"}),
            frozenset({("same", "same")}),
        ),
        (
            (("event A", "alpha"), ("event B", "beta")),
            frozenset({"alpha", "beta"}),
            frozenset(),
        ),
    ],
)
def test_lexical_projection_is_undefined_without_all_declared_conditions(
    lexical_handles: tuple[tuple[str, str], ...],
    represented_terms: frozenset[str],
    observed_term_pairs: frozenset[tuple[str, str]],
) -> None:
    certificate = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            frozenset({EvidenceChannel.CO_OCCURRENCE}),
            governed_object=GovernedObject(
                "event A", ObjectType.EVENT, "event B", ObjectType.EVENT
            ),
            lexical_handles=lexical_handles,
            represented_terms=represented_terms,
            observed_term_pairs=observed_term_pairs,
        ),
    )

    assert certificate.fallback_claim is None
    assert certificate.fallback_projection is None
    assert certificate.allowed_encoding is VisualEncoding.NO_RELATION


def test_adding_required_evidence_upgrades_temporal_claim() -> None:
    refused = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(frozenset({EvidenceChannel.CO_OCCURRENCE})),
    )
    admitted = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            frozenset({EvidenceChannel.CO_OCCURRENCE, EvidenceChannel.EVENT_ORDER})
        ),
    )

    assert refused.decision is Decision.REFUSE
    assert refused.observational_identifiability is False
    assert admitted.decision is Decision.ADMIT
    assert admitted.observational_identifiability is False
    assert admitted.allowed_encoding is VisualEncoding.DIRECTED_ARROW


def test_independent_identifying_channel_does_not_relabel_observation_model() -> None:
    certificate = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.EVENT_ORDER,
                    target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
                    relation=("event A", "event B"),
                ),
            ),
            governed_object=GovernedObject(
                "event A", ObjectType.EVENT, "event B", ObjectType.EVENT
            ),
        ),
    )

    assert certificate.observational_identifiability is None
    assert certificate.policy_admissible is True
    assert certificate.decision is Decision.ADMIT


def test_noninterventional_direction_does_not_substitute_for_causal_evidence() -> None:
    certificate = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        EvidenceBundle(
            frozenset(
                {
                    EvidenceChannel.ORDER,
                    EvidenceChannel.SYNTAX,
                    EvidenceChannel.CROSS_REFERENCE,
                    EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                }
            )
        ),
    )

    assert certificate.decision is Decision.REFUSE
    assert certificate.allowed_encoding is VisualEncoding.NO_RELATION


def test_asymmetric_conditional_is_qualified_even_when_checks_pass() -> None:
    certificate = evaluate_claim(
        ClaimType.ASYMMETRIC_CONDITIONAL,
        EvidenceBundle(
            frozenset({EvidenceChannel.CO_OCCURRENCE}),
            specification_survival=1.0,
        ),
    )

    assert certificate.decision is Decision.QUALIFY
    assert (
        certificate.allowed_encoding
        is VisualEncoding.CONDITIONAL_ASYMMETRY_GLYPH
    )
    assert "marginal prevalence" in certificate.witness[0]


def test_interpretive_claims_require_design_metadata() -> None:
    bare_theme = evaluate_claim(
        ClaimType.THEME,
        EvidenceBundle(frozenset({EvidenceChannel.QUALITATIVE_INTERPRETATION})),
    )
    traceable_theme = evaluate_claim(
        ClaimType.THEME,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.QUALITATIVE_INTERPRETATION,
                    target=ClaimType.THEME,
                    method="reflexive thematic analysis",
                    analytic_traceability="coded excerpts to candidate theme",
                    reflexive_documentation="researcher position memo",
                    theory_alignment="declared research question and framework",
                    adjudication_status=AdjudicationStatus.APPROVED,
                ),
            ),
        ),
    )
    bare_benefit = evaluate_claim(
        ClaimType.ANALYST_BENEFIT,
        EvidenceBundle(frozenset({EvidenceChannel.HUMAN_EVALUATION})),
    )

    assert bare_theme.decision is Decision.REFUSE
    assert traceable_theme.decision is Decision.ADMIT
    assert bare_benefit.decision is Decision.REFUSE


def test_unscoped_meta_claim_does_not_select_pair_fallback() -> None:
    certificate = evaluate_claim(
        ClaimType.STATISTICAL_STABILITY,
        EvidenceBundle(frozenset({EvidenceChannel.CO_OCCURRENCE})),
    )

    assert certificate.decision is Decision.REFUSE
    assert certificate.fallback_claim is None
    assert certificate.allowed_encoding is VisualEncoding.NO_RELATION


def test_incomplete_provenance_refuses_an_identifiable_claim() -> None:
    certificate = evaluate_claim(
        ClaimType.LEXICAL_ASSOCIATION,
        EvidenceBundle(
            frozenset({EvidenceChannel.CO_OCCURRENCE}),
            provenance_complete=False,
        ),
    )

    assert certificate.identifiable is True
    assert certificate.decision is Decision.REFUSE
    assert certificate.allowed_encoding is VisualEncoding.NO_RELATION


def test_annotation_must_match_requested_construct() -> None:
    certificate = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE})
        ),
    )

    assert certificate.identifiable is False
    assert certificate.decision is Decision.REFUSE


def test_semantic_annotation_admits_only_its_claim() -> None:
    evidence = EvidenceBundle(
        frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE})
    )

    assert evaluate_claim(ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, evidence).decision is Decision.ADMIT
    assert evaluate_claim(ClaimType.CONCEPT_PREREQUISITE, evidence).decision is Decision.REFUSE


def test_symmetric_equivalence_evidence_matches_reversed_pair() -> None:
    certificate = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                    target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
                    relation=("sentence-a", "sentence-b"),
                ),
            ),
            requested_relation=("sentence-b", "sentence-a"),
        ),
    )

    assert certificate.identifiable is True
    assert certificate.decision is Decision.ADMIT


def test_ordered_prerequisite_evidence_does_not_match_reversed_pair() -> None:
    certificate = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.PREREQUISITE_REFERENCE,
                    target=ClaimType.CONCEPT_PREREQUISITE,
                    relation=("foundations", "methods"),
                ),
            ),
            requested_relation=("methods", "foundations"),
        ),
    )

    assert certificate.identifiable is False
    assert certificate.decision is Decision.REFUSE


def test_claim_requires_compatible_governed_object_types() -> None:
    relation = ("rain started", "roads flooded")
    evidence = EvidenceRecord(
        channel=EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
        target=ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        relation=relation,
    )

    correctly_typed = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            records=(evidence,),
            governed_object=GovernedObject(
                relation[0], ObjectType.EVENT, relation[1], ObjectType.EVENT
            ),
        ),
    )
    incorrectly_typed = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(
            records=(evidence,),
            governed_object=GovernedObject(
                relation[0], ObjectType.SENTENCE, relation[1], ObjectType.SENTENCE
            ),
        ),
    )

    assert correctly_typed.decision is Decision.ADMIT
    assert incorrectly_typed.identifiable is False
    assert incorrectly_typed.decision is Decision.REFUSE


def test_negative_semantic_annotation_defeats_positive_claim() -> None:
    certificate = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                    target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
                    polarity=EvidencePolarity.COUNTEREVIDENCE,
                    source="human label: non-paraphrase",
                ),
            ),
        ),
    )

    assert certificate.decision is Decision.REFUSE
    assert certificate.allowed_export is False


def test_statistical_stability_requires_bootstrap_and_dependence_evidence() -> None:
    missing = evaluate_claim(
        ClaimType.STATISTICAL_STABILITY,
        EvidenceBundle(frozenset({EvidenceChannel.CO_OCCURRENCE})),
    )
    inadequate = evaluate_claim(
        ClaimType.STATISTICAL_STABILITY,
        EvidenceBundle(frozenset({EvidenceChannel.CLUSTER_BOOTSTRAP})),
    )
    adequate = evaluate_claim(
        ClaimType.STATISTICAL_STABILITY,
        EvidenceBundle(
            frozenset({EvidenceChannel.CLUSTER_BOOTSTRAP}),
            uncertainty_adequate=True,
            dependence_adequate=True,
        ),
    )

    assert missing.decision is Decision.REFUSE
    assert inadequate.decision is Decision.REFUSE
    assert ReasonCode.EVIDENCE_CHANNEL_ABSENT not in inadequate.reason_codes
    assert ReasonCode.UNCERTAINTY_INADEQUATE in inadequate.reason_codes
    assert ReasonCode.DEPENDENCE_INADEQUATE in inadequate.reason_codes
    assert inadequate.triggered_reasons == inadequate.reason_codes
    assert inadequate.decision_reason is ReasonCode.UNCERTAINTY_INADEQUATE
    assert adequate.decision is Decision.ADMIT


def test_descriptive_bootstrap_persistence_is_distinct_from_stability() -> None:
    evidence = EvidenceBundle(frozenset({EvidenceChannel.CLUSTER_BOOTSTRAP}))

    persistence = evaluate_claim(ClaimType.BOOTSTRAP_PERSISTENCE, evidence)
    stability = evaluate_claim(ClaimType.STATISTICAL_STABILITY, evidence)

    assert persistence.decision is Decision.ADMIT
    assert stability.decision is Decision.REFUSE


def test_specification_persistence_is_distinct_from_statistical_stability() -> None:
    evidence = EvidenceBundle(
        frozenset(
            {
                EvidenceChannel.CO_OCCURRENCE,
                EvidenceChannel.SPECIFICATION_SURFACE,
            }
        ),
        specification_survival=0.65,
    )

    persistence = evaluate_claim(ClaimType.SPECIFICATION_PERSISTENCE, evidence)
    gate = evaluate_claim(ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE, evidence)
    stability = evaluate_claim(ClaimType.STATISTICAL_STABILITY, evidence)

    assert persistence.decision is Decision.ADMIT
    assert gate.decision is Decision.REFUSE
    assert stability.decision is Decision.REFUSE


def test_specification_gate_refusal_reports_observed_value() -> None:
    channels = frozenset({EvidenceChannel.SPECIFICATION_SURFACE})
    highly_sensitive = evaluate_claim(
        ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE,
        EvidenceBundle(channels, specification_survival=1 / 24),
    )
    near_threshold = evaluate_claim(
        ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE,
        EvidenceBundle(channels, specification_survival=19 / 24),
    )

    assert highly_sensitive.decision is Decision.REFUSE
    assert near_threshold.decision is Decision.REFUSE
    assert ReasonCode.EVIDENCE_CHANNEL_ABSENT not in highly_sensitive.reason_codes
    assert ReasonCode.PERSISTENCE_GATE_FAILED in highly_sensitive.reason_codes
    assert any("S=0.042" in item for item in highly_sensitive.witness)
    assert any("S=0.792" in item for item in near_threshold.witness)


def test_policy_2_2_requires_parameterized_causal_identification() -> None:
    bare = EvidenceBundle(frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION}))
    declared = EvidenceBundle(
        frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION}),
        causal_method="back-door adjustment",
        causal_assumptions=("conditional exchangeability", "positivity"),
        causal_estimand="average treatment effect",
        causal_design="observational adjustment",
        causal_diagnostics="positivity and balance diagnostics passed",
    )

    assert evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE, bare, policy_version="2.0.0"
    ).decision is Decision.ADMIT
    assert evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE, bare, policy_version="2.1.0"
    ).decision is Decision.REFUSE
    assert evaluate_claim(ClaimType.CAUSAL_INFLUENCE, bare).decision is Decision.REFUSE
    assert evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE, declared, policy_version="2.5.0"
    ).decision is Decision.ADMIT
    assert evaluate_claim(ClaimType.CAUSAL_INFLUENCE, declared).decision is Decision.REFUSE


def test_mention_order_does_not_identify_event_temporal_precedence() -> None:
    mention_order = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(frozenset({EvidenceChannel.MENTION_ORDER})),
    )
    event_order = evaluate_claim(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceBundle(frozenset({EvidenceChannel.EVENT_ORDER})),
    )

    assert mention_order.identifiable is False
    assert mention_order.decision is Decision.REFUSE
    assert ReasonCode.MENTION_ORDER_INSUFFICIENT in mention_order.triggered_reasons
    assert mention_order.decision_reason is ReasonCode.MENTION_ORDER_INSUFFICIENT
    assert event_order.decision is Decision.ADMIT


def test_generic_cross_reference_does_not_identify_prerequisite() -> None:
    generic = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(frozenset({EvidenceChannel.CROSS_REFERENCE})),
    )
    prerequisite = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(frozenset({EvidenceChannel.PREREQUISITE_REFERENCE})),
    )

    assert generic.identifiable is False
    assert generic.decision is Decision.REFUSE
    assert prerequisite.decision is Decision.ADMIT


def test_causal_metadata_is_part_of_identifiability_predicate() -> None:
    bare = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        EvidenceBundle(frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION})),
    )
    declared_bundle = EvidenceBundle(
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.CAUSAL_IDENTIFICATION,
                target=ClaimType.CAUSAL_INFLUENCE,
                method="back-door adjustment",
                assumptions=("conditional exchangeability", "positivity"),
                estimand="average treatment effect",
                study_design="observational adjustment",
                diagnostics="positivity and balance diagnostics passed",
                source="authored causal design",
            ),
        )
    )
    declared = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        declared_bundle,
    )
    adjudicated = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.CAUSAL_IDENTIFICATION,
                    target=ClaimType.CAUSAL_INFLUENCE,
                    method="back-door adjustment",
                    assumptions=("conditional exchangeability", "positivity"),
                    estimand="average treatment effect",
                    study_design="observational adjustment",
                    diagnostics="positivity and balance diagnostics passed",
                    source="authored causal design",
                    adjudication_status=AdjudicationStatus.APPROVED,
                ),
            )
        ),
    )

    assert bare.identifiable is False
    assert declared.identifiable is False
    assert declared.decision is Decision.REFUSE
    assert ReasonCode.ADJUDICATION_REQUIRED in declared.reason_codes
    assert adjudicated.identifiable is True
    assert adjudicated.decision is Decision.ADMIT
    assert evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        declared_bundle,
        policy_version="2.5.0",
    ).decision is Decision.ADMIT


def test_intervention_is_not_independently_sufficient_for_causal_influence() -> None:
    intervention_only = evaluate_claim(
        ClaimType.CAUSAL_INFLUENCE,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.INTERVENTION,
                    target=ClaimType.CAUSAL_INFLUENCE,
                    method="randomized intervention",
                    assumptions=("consistency", "no interference"),
                    estimand="average treatment effect",
                    study_design="randomized intervention",
                    diagnostics="allocation and attrition checks passed",
                ),
            ),
        ),
    )

    assert intervention_only.identifiable is False
    assert intervention_only.decision is Decision.REFUSE


def test_interpretive_claims_require_external_adjudication() -> None:
    theme_record = EvidenceRecord(
        channel=EvidenceChannel.QUALITATIVE_INTERPRETATION,
        target=ClaimType.THEME,
        method="reflexive thematic analysis",
        analytic_traceability="coded excerpts to candidate theme",
        reflexive_documentation="researcher position memo",
        theory_alignment="declared research question and framework",
    )

    provisional = evaluate_claim(
        ClaimType.THEME,
        EvidenceBundle(records=(theme_record,)),
    )
    adjudicated = evaluate_claim(
        ClaimType.THEME,
        EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=theme_record.channel,
                    target=theme_record.target,
                    method=theme_record.method,
                    analytic_traceability=theme_record.analytic_traceability,
                    reflexive_documentation=theme_record.reflexive_documentation,
                    theory_alignment=theme_record.theory_alignment,
                    adjudication_status=AdjudicationStatus.APPROVED,
                ),
            ),
        ),
    )

    assert provisional.decision is Decision.REFUSE
    assert adjudicated.decision is Decision.ADMIT


def test_bundle_predicate_can_conjoin_metadata_across_records() -> None:
    evidence = EvidenceBundle(
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.CAUSAL_IDENTIFICATION,
                target=ClaimType.CAUSAL_INFLUENCE,
                method="back-door adjustment",
                    study_design="observational adjustment",
                source="design record",
            ),
            EvidenceRecord(
                channel=EvidenceChannel.CAUSAL_IDENTIFICATION,
                target=ClaimType.CAUSAL_INFLUENCE,
                assumptions=("conditional exchangeability", "positivity"),
                estimand="average treatment effect",
                diagnostics="positivity and balance diagnostics passed",
                source="estimand record",
                adjudication_status=AdjudicationStatus.APPROVED,
            ),
        )
    )

    certificate = evaluate_claim(ClaimType.CAUSAL_INFLUENCE, evidence)

    assert certificate.identifiable is True
    assert certificate.decision is Decision.ADMIT


def test_claim_certificates_expose_stable_claim_families() -> None:
    lexical = evaluate_claim(
        ClaimType.LEXICAL_ASSOCIATION,
        EvidenceBundle(frozenset({EvidenceChannel.CO_OCCURRENCE})),
    )
    causal = evaluate_claim(ClaimType.CAUSAL_INFLUENCE, EvidenceBundle())

    assert lexical.claim_family is ClaimFamily.OBSERVATIONAL
    assert causal.claim_family is ClaimFamily.CAUSAL
    assert lexical.as_dict()["claim_family"] == "observational"


def test_support_counterevidence_truth_table() -> None:
    support = EvidenceRecord(
        channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
        target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        polarity=EvidencePolarity.SUPPORT,
        source="documented annotation protocol",
    )
    counter = EvidenceRecord(
        channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
        target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        polarity=EvidencePolarity.COUNTEREVIDENCE,
        source="documented annotation protocol",
    )

    neither = evaluate_claim(ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, EvidenceBundle())
    support_only = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, EvidenceBundle(records=(support,))
    )
    counter_only = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, EvidenceBundle(records=(counter,))
    )
    conflict = evaluate_claim(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        EvidenceBundle(records=(support, counter)),
    )

    assert neither.decision is Decision.REFUSE
    assert support_only.decision is Decision.ADMIT
    assert counter_only.decision is Decision.REFUSE
    assert conflict.decision is Decision.QUALIFY
    assert ReasonCode.CONFLICT_PRESENT in conflict.reason_codes
    assert conflict.triggered_reasons == (ReasonCode.CONFLICT_PRESENT,)
    assert conflict.decision_reason is ReasonCode.CONFLICT_PRESENT
    assert conflict.allowed_encoding is VisualEncoding.CONTESTED_RELATION
    assert conflict.allowed_export is False


def test_pair_scoped_evidence_does_not_transfer_to_reverse_relation() -> None:
    forward_relation = ("foundational concept", "advanced concept")
    reverse_relation = tuple(reversed(forward_relation))
    annotation = EvidenceRecord(
        channel=EvidenceChannel.ANNOTATION_PREREQUISITE,
        target=ClaimType.CONCEPT_PREREQUISITE,
        relation=forward_relation,
        source="documented external prerequisite annotation",
    )

    forward = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(records=(annotation,), requested_relation=forward_relation),
    )
    reverse = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(records=(annotation,), requested_relation=reverse_relation),
    )
    replay = evaluate_claim(
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceBundle(records=(annotation,), requested_relation=reverse_relation),
        policy_version="2.2.0",
    )

    assert forward.decision is Decision.ADMIT
    assert forward.requested_relation == forward_relation
    assert reverse.decision is Decision.REFUSE
    assert reverse.identifiable is False
    assert replay.decision is Decision.ADMIT