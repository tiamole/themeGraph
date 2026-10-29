"""Executable policies governing claims, encodings, exports, and remediation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any

POLICY_VERSION = "2.7.0"
SUPPORTED_POLICY_VERSIONS = frozenset(
    {
        "2.0.0",
        "2.1.0",
        "2.2.0",
        "2.3.0",
        "2.4.0",
        "2.5.0",
        "2.6.0",
        POLICY_VERSION,
    }
)
_RELATION_SCOPED_POLICY_VERSIONS = frozenset(
    {"2.3.0", "2.4.0", "2.5.0", "2.6.0", POLICY_VERSION}
)
_TYPED_OBJECT_POLICY_VERSIONS = frozenset({"2.5.0", "2.6.0", POLICY_VERSION})
_ADEQUACY_GATE_POLICY_VERSIONS = frozenset({"2.5.0", "2.6.0", POLICY_VERSION})


class EvidenceChannel(StrEnum):
    CO_OCCURRENCE = "co-occurrence"
    ORDER = "order"
    MENTION_ORDER = "mention-order"
    EVENT_ORDER = "event-order"
    SYNTAX = "syntax"
    DISCOURSE = "discourse"
    CROSS_REFERENCE = "cross-reference"
    PREREQUISITE_REFERENCE = "prerequisite-reference"
    ANNOTATION_SEMANTIC_EQUIVALENCE = "annotation-semantic-equivalence"
    ANNOTATION_TEMPORAL_PRECEDENCE = "annotation-temporal-precedence"
    ANNOTATION_PREREQUISITE = "annotation-prerequisite"
    ANNOTATION_ENTAILMENT = "annotation-entailment"
    QUALITATIVE_INTERPRETATION = "qualitative-interpretation"
    CAUSAL_IDENTIFICATION = "causal-identification"
    INTERVENTION = "intervention"
    HUMAN_EVALUATION = "human-evaluation"
    SPECIFICATION_SURFACE = "specification-surface"
    CLUSTER_BOOTSTRAP = "cluster-bootstrap"


class ClaimType(StrEnum):
    LEXICAL_ASSOCIATION = "lexical-association"
    ASYMMETRIC_CONDITIONAL = "asymmetric-conditional"
    SENTENTIAL_PARAPHRASE_EQUIVALENCE = "sentential-paraphrase-equivalence"
    SENTENTIAL_NON_PARAPHRASE = "sentential-non-paraphrase"
    CONCEPT_EQUIVALENCE = "concept-equivalence"
    TEXTUAL_ENTAILMENT = "textual-entailment"
    EVENT_TEMPORAL_PRECEDENCE = "event-temporal-precedence"
    CONCEPT_PREREQUISITE = "concept-prerequisite"
    CAUSAL_INFLUENCE = "causal-influence"
    THEME = "theme"
    ANALYST_BENEFIT = "analyst-benefit"
    SPECIFICATION_PERSISTENCE = "specification-persistence"
    MEETS_SPECIFICATION_PERSISTENCE_GATE = "meets-specification-persistence-gate"
    BOOTSTRAP_PERSISTENCE = "bootstrap-persistence-under-declared-scheme"
    STATISTICAL_STABILITY = "statistical-stability"


class ClaimFamily(StrEnum):
    OBSERVATIONAL = "observational"
    STATISTICAL = "statistical"
    SEMANTIC_RELATIONAL = "semantic-relational"
    CAUSAL = "causal"
    INTERPRETIVE = "interpretive"
    HUMAN_OUTCOME = "human-outcome"


class ObjectType(StrEnum):
    TERM = "term"
    SENTENCE = "sentence"
    EVENT = "event"
    CONCEPT = "concept"
    INTERVENTION = "intervention"
    OUTCOME = "outcome"
    ANALYSIS = "analysis"
    THEME_CANDIDATE = "theme-candidate"
    INTERFACE = "interface"
    ANALYST_POPULATION = "analyst-population"
    RESULT = "result"
    SPECIFICATION_SURFACE = "specification-surface"
    RESAMPLING_SCHEME = "resampling-scheme"


class AdjudicationStatus(StrEnum):
    NOT_REVIEWED = "not-reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvidencePolarity(StrEnum):
    SUPPORT = "support"
    COUNTEREVIDENCE = "counterevidence"


class RelationScope(StrEnum):
    SYMMETRIC = "symmetric"
    ORDERED = "ordered"
    UNSCOPED = "unscoped"


class Decision(StrEnum):
    ADMIT = "ADMIT"
    QUALIFY = "QUALIFY"
    REFUSE = "REFUSE"


class ReasonCode(StrEnum):
    EVIDENCE_CHANNEL_ABSENT = "evidence-channel-absent"
    SUPPORT_EVIDENCE_ABSENT = "support-evidence-absent"
    EVIDENCE_TARGET_MISMATCH = "evidence-target-mismatch"
    RELATION_SCOPE_MISMATCH = "relation-scope-mismatch"
    PREDICATE_METADATA_INCOMPLETE = "predicate-metadata-incomplete"
    OBJECT_TYPE_MISMATCH = "object-type-mismatch"
    ADJUDICATION_REQUIRED = "adjudication-required"
    PERSISTENCE_GATE_FAILED = "persistence-gate-failed"
    UNCERTAINTY_INADEQUATE = "uncertainty-inadequate"
    DEPENDENCE_INADEQUATE = "dependence-inadequate"
    PROVENANCE_INCOMPLETE = "provenance-incomplete"
    PREVALENCE_QUALIFICATION = "prevalence-qualification"
    PERSISTENCE_QUALIFICATION = "persistence-qualification"
    CONFLICT_PRESENT = "conflict-present"
    MENTION_ORDER_INSUFFICIENT = "mention-order-insufficient"


class RefusalClass(StrEnum):
    EPISTEMIC = "epistemic"
    POLICY = "policy"
    OPERATIONAL = "operational"


class VisualEncoding(StrEnum):
    UNDIRECTED_LINK = "undirected-link"
    CONDITIONAL_ASYMMETRY_GLYPH = "conditional-asymmetry-glyph"
    DIRECTED_ARROW = "directed-arrow"
    CONTESTED_RELATION = "contested-relation"
    NO_RELATION = "no-relation"


@dataclass(frozen=True, slots=True)
class GovernedObject:
    source: str
    source_type: ObjectType
    target: str
    target_type: ObjectType

    @property
    def relation(self) -> tuple[str, str]:
        return (self.source, self.target)

    @property
    def signature(self) -> tuple[ObjectType, ObjectType]:
        return (self.source_type, self.target_type)


@dataclass(frozen=True, slots=True)
class FallbackProjection:
    projection_id: str
    source_claim: ClaimType
    target_claim: ClaimType
    target_signature: tuple[ObjectType, ObjectType]
    preserves_labels: bool = False
    preserves_provenance: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    channel: EvidenceChannel
    target: ClaimType | None = None
    polarity: EvidencePolarity = EvidencePolarity.SUPPORT
    relation: tuple[str, str] | None = None
    scope: str = ""
    source: str = ""
    method: str = ""
    assumptions: tuple[str, ...] = ()
    estimand: str = ""
    quality: str = ""
    analytic_traceability: str = ""
    reflexive_documentation: str = ""
    theory_alignment: str = ""
    outcome: str = ""
    measure: str = ""
    study_design: str = ""
    comparator: str = ""
    population: str = ""
    diagnostics: str = ""
    adjudication_status: AdjudicationStatus = AdjudicationStatus.NOT_REVIEWED
    independent: bool | None = None


@dataclass(frozen=True, slots=True)
class EvidencePredicate:
    predicate_id: str
    channels: frozenset[EvidenceChannel]
    description: str
    target: ClaimType | None = None
    required_metadata: tuple[str, ...] = ()
    requires_approved_adjudication: bool = False


@dataclass(frozen=True, slots=True)
class ClaimPolicy:
    claim_type: ClaimType
    required_alternatives: tuple[frozenset[EvidenceChannel], ...]
    allowed_encoding: VisualEncoding
    allowed_statement: str
    remediation: str
    force_qualification: str = ""
    requires_uncertainty: bool = False
    requires_independence: bool = False
    predicates: tuple[EvidencePredicate, ...] = ()
    allow_refused_export: bool = False
    object_signatures: tuple[tuple[ObjectType, ObjectType], ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    channels: frozenset[EvidenceChannel] = frozenset()
    records: tuple[EvidenceRecord, ...] = ()
    requested_relation: tuple[str, str] | None = None
    governed_object: GovernedObject | None = None
    provenance_complete: bool = True
    specification_survival: float | None = None
    minimum_survival: float = 0.8
    uncertainty_adequate: bool = False
    dependence_adequate: bool = False
    counterevidence: tuple[str, ...] = ()
    causal_method: str = ""
    causal_assumptions: tuple[str, ...] = ()
    causal_estimand: str = ""
    causal_design: str = ""
    causal_diagnostics: str = ""
    lexical_handles: tuple[tuple[str, str], ...] = ()
    represented_terms: frozenset[str] = frozenset()
    observed_term_pairs: frozenset[tuple[str, str]] = frozenset()

    def __post_init__(self) -> None:
        if self.governed_object is not None:
            if (
                self.requested_relation is not None
                and self.requested_relation != self.governed_object.relation
            ):
                raise ValueError(
                    "requested_relation must match the governed object relation"
                )
            object.__setattr__(self, "requested_relation", self.governed_object.relation)
        for value, name in (
            (self.specification_survival, "specification_survival"),
            (self.minimum_survival, "minimum_survival"),
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    @property
    def observed_channels(self) -> frozenset[EvidenceChannel]:
        return self.channels | frozenset(record.channel for record in self.records)

    def evidence_records(self) -> tuple[EvidenceRecord, ...]:
        explicit_channels = {record.channel for record in self.records}
        inherited = tuple(
            EvidenceRecord(
                channel=channel,
                relation=self.requested_relation,
                method=(
                    self.causal_method if channel in _CAUSAL_CHANNELS else ""
                ),
                assumptions=(
                    self.causal_assumptions if channel in _CAUSAL_CHANNELS else ()
                ),
                estimand=(
                    self.causal_estimand if channel in _CAUSAL_CHANNELS else ""
                ),
                study_design=(
                    self.causal_design if channel in _CAUSAL_CHANNELS else ""
                ),
                diagnostics=(
                    self.causal_diagnostics if channel in _CAUSAL_CHANNELS else ""
                ),
            )
            for channel in self.channels
            if channel not in explicit_channels
        )
        return self.records + inherited


@dataclass(frozen=True, slots=True)
class ClaimCertificate:
    policy_version: str
    claim_type: ClaimType
    claim_family: ClaimFamily
    requested_relation: tuple[str, str] | None
    governed_object: GovernedObject | None
    required_object_signatures: tuple[tuple[ObjectType, ObjectType], ...]
    object_type_match: bool
    adjudication_required: bool
    adjudication_approved: bool
    required_alternatives: tuple[frozenset[EvidenceChannel], ...]
    required_predicates: tuple[EvidencePredicate, ...]
    observed_channels: frozenset[EvidenceChannel]
    observational_identifiability: bool | None
    identifiable: bool
    policy_admissible: bool
    reason_codes: tuple[ReasonCode, ...]
    triggered_reasons: tuple[ReasonCode, ...]
    decision_reason: ReasonCode | None
    refusal_class: RefusalClass | None
    provenance_complete: bool
    specification_survival: float | None
    uncertainty_adequate: bool
    dependence_adequate: bool
    counterevidence: tuple[str, ...]
    causal_method: str
    causal_assumptions: tuple[str, ...]
    causal_estimand: str
    causal_design: str
    causal_diagnostics: str
    decision: Decision
    allowed_encoding: VisualEncoding
    allowed_statement: str
    allowed_export: bool
    requested_representation_authorized: bool
    fallback_claim: ClaimType | None
    fallback_decision: Decision | None
    fallback_allowed_export: bool | None
    fallback_is_policy_preferred: bool
    fallback_projection: str | None
    fallback_projected_object: GovernedObject | None
    fallback_projection_provenance: tuple[str, ...]
    witness: tuple[str, ...]
    remediation: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["claim_type"] = self.claim_type.value
        payload["claim_family"] = self.claim_family.value
        payload["requested_relation"] = (
            list(self.requested_relation) if self.requested_relation else None
        )
        if self.governed_object is not None:
            payload["governed_object"] = {
                "source": self.governed_object.source,
                "source_type": self.governed_object.source_type.value,
                "target": self.governed_object.target,
                "target_type": self.governed_object.target_type.value,
            }
        payload["required_object_signatures"] = [
            [source_type.value, target_type.value]
            for source_type, target_type in self.required_object_signatures
        ]
        payload["required_alternatives"] = [
            sorted(channel.value for channel in alternative)
            for alternative in self.required_alternatives
        ]
        payload["required_predicates"] = [
            {
                "predicate_id": predicate.predicate_id,
                "channels": sorted(
                    channel.value for channel in predicate.channels
                ),
                "description": predicate.description,
                "target": predicate.target.value if predicate.target else None,
                "required_metadata": list(predicate.required_metadata),
                "requires_approved_adjudication": (
                    predicate.requires_approved_adjudication
                ),
            }
            for predicate in self.required_predicates
        ]
        payload["observed_channels"] = sorted(
            channel.value for channel in self.observed_channels
        )
        payload["decision"] = self.decision.value
        payload["reason_codes"] = [reason.value for reason in self.reason_codes]
        payload["triggered_reasons"] = [
            reason.value for reason in self.triggered_reasons
        ]
        payload["decision_reason"] = (
            self.decision_reason.value if self.decision_reason is not None else None
        )
        payload["refusal_class"] = (
            self.refusal_class.value if self.refusal_class is not None else None
        )
        payload["allowed_encoding"] = self.allowed_encoding.value
        payload["fallback_claim"] = (
            self.fallback_claim.value if self.fallback_claim is not None else None
        )
        payload["fallback_decision"] = (
            self.fallback_decision.value
            if self.fallback_decision is not None
            else None
        )
        if self.fallback_projected_object is not None:
            payload["fallback_projected_object"] = {
                "source": self.fallback_projected_object.source,
                "source_type": self.fallback_projected_object.source_type.value,
                "target": self.fallback_projected_object.target,
                "target_type": self.fallback_projected_object.target_type.value,
            }
        return payload


POLICIES = {
    ClaimType.LEXICAL_ASSOCIATION: ClaimPolicy(
        ClaimType.LEXICAL_ASSOCIATION,
        (frozenset({EvidenceChannel.CO_OCCURRENCE}),),
        VisualEncoding.UNDIRECTED_LINK,
        "The terms have a thresholded lexical association under this configuration.",
        "Supply within-unit co-occurrence evidence with complete lineage.",
        object_signatures=((ObjectType.TERM, ObjectType.TERM),),
    ),
    ClaimType.ASYMMETRIC_CONDITIONAL: ClaimPolicy(
        ClaimType.ASYMMETRIC_CONDITIONAL,
        (frozenset({EvidenceChannel.CO_OCCURRENCE}),),
        VisualEncoding.CONDITIONAL_ASYMMETRY_GLYPH,
        "The conditional confidence differs by orientation under this configuration.",
        "Supply a directional evidence channel to request semantic direction.",
        "Orientation is determined by marginal prevalence, not directional observation.",
        object_signatures=((ObjectType.TERM, ObjectType.TERM),),
    ),
    ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE: ClaimPolicy(
        ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
        (frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE}),),
        VisualEncoding.UNDIRECTED_LINK,
        "The sentence pair is paraphrase-equivalent under the declared annotation protocol.",
        "Supply a construct-matched sentential paraphrase annotation.",
        predicates=(
            EvidencePredicate(
                "construct-matched-support",
                frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE}),
                "annotation-semantic-equivalence with matched positive paraphrase label",
                ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
            ),
        ),
        object_signatures=((ObjectType.SENTENCE, ObjectType.SENTENCE),),
    ),
    ClaimType.SENTENTIAL_NON_PARAPHRASE: ClaimPolicy(
        ClaimType.SENTENTIAL_NON_PARAPHRASE,
        (frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE}),),
        VisualEncoding.NO_RELATION,
        "The sentence pair was not judged a paraphrase under the declared annotation protocol.",
        "Supply a construct-matched negative sentential paraphrase annotation.",
        predicates=(
            EvidencePredicate(
                "construct-matched-support",
                frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE}),
                "annotation-semantic-equivalence with matched non-paraphrase label",
                ClaimType.SENTENTIAL_NON_PARAPHRASE,
            ),
        ),
        object_signatures=((ObjectType.SENTENCE, ObjectType.SENTENCE),),
    ),
    ClaimType.CONCEPT_EQUIVALENCE: ClaimPolicy(
        ClaimType.CONCEPT_EQUIVALENCE,
        (frozenset({EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE}),),
        VisualEncoding.UNDIRECTED_LINK,
        "The concept pair was judged equivalent under the declared annotation protocol.",
        "Supply a construct-matched concept-equivalence annotation.",
        object_signatures=((ObjectType.CONCEPT, ObjectType.CONCEPT),),
    ),
    ClaimType.TEXTUAL_ENTAILMENT: ClaimPolicy(
        ClaimType.TEXTUAL_ENTAILMENT,
        (frozenset({EvidenceChannel.ANNOTATION_ENTAILMENT}),),
        VisualEncoding.DIRECTED_ARROW,
        "The premise entails the hypothesis under the declared annotation protocol.",
        "Supply a construct-matched directional entailment annotation.",
        object_signatures=((ObjectType.SENTENCE, ObjectType.SENTENCE),),
    ),
    ClaimType.EVENT_TEMPORAL_PRECEDENCE: ClaimPolicy(
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        (
            frozenset({EvidenceChannel.EVENT_ORDER}),
            frozenset({EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE}),
        ),
        VisualEncoding.DIRECTED_ARROW,
        "The source precedes the target in the declared temporal observation.",
        "Supply observed event order or a construct-matched temporal annotation.",
        object_signatures=((ObjectType.EVENT, ObjectType.EVENT),),
    ),
    ClaimType.CONCEPT_PREREQUISITE: ClaimPolicy(
        ClaimType.CONCEPT_PREREQUISITE,
        (
            frozenset({EvidenceChannel.PREREQUISITE_REFERENCE}),
            frozenset({EvidenceChannel.ANNOTATION_PREREQUISITE}),
        ),
        VisualEncoding.DIRECTED_ARROW,
        "The source concept is an explicit prerequisite for the target concept.",
        "Supply a concept-prerequisite reference or construct-matched annotation.",
        object_signatures=((ObjectType.CONCEPT, ObjectType.CONCEPT),),
    ),
    ClaimType.CAUSAL_INFLUENCE: ClaimPolicy(
        ClaimType.CAUSAL_INFLUENCE,
        (frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION}),),
        VisualEncoding.DIRECTED_ARROW,
        "The declared identifying design and assumptions support a causal influence claim.",
        "Supply a causal-identification design with a named method, assumptions, estimand, and diagnostics; intervention may be the design subtype.",
        predicates=(
            EvidencePredicate(
                "causal-identification-record",
                frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION}),
                "causal identification with named design, method, assumptions, target estimand, and diagnostics",
                ClaimType.CAUSAL_INFLUENCE,
                ("method", "assumptions", "estimand", "study_design", "diagnostics"),
                True,
            ),
        ),
        object_signatures=((ObjectType.INTERVENTION, ObjectType.OUTCOME),),
    ),
    ClaimType.THEME: ClaimPolicy(
        ClaimType.THEME,
        (
            frozenset({EvidenceChannel.QUALITATIVE_INTERPRETATION}),
        ),
        VisualEncoding.NO_RELATION,
        "A researcher interpreted the candidate as a theme under the declared qualitative method.",
        "Supply reflexive interpretation, theoretical coherence, and analytic traceability.",
        predicates=(
            EvidencePredicate(
                "traceable-qualitative-interpretation",
                frozenset({EvidenceChannel.QUALITATIVE_INTERPRETATION}),
                "qualitative interpretation with method, analytic traceability, reflexive documentation, and theory alignment",
                ClaimType.THEME,
                (
                    "method",
                    "analytic_traceability",
                    "reflexive_documentation",
                    "theory_alignment",
                ),
                True,
            ),
        ),
        object_signatures=((ObjectType.ANALYSIS, ObjectType.THEME_CANDIDATE),),
    ),
    ClaimType.ANALYST_BENEFIT: ClaimPolicy(
        ClaimType.ANALYST_BENEFIT,
        (frozenset({EvidenceChannel.HUMAN_EVALUATION}),),
        VisualEncoding.NO_RELATION,
        "The evaluated interface supports the named analyst outcome.",
        "Supply a human evaluation with a prespecified outcome, valid measure, study design, comparator, target population, and estimand.",
        predicates=(
            EvidencePredicate(
                "identified-analyst-benefit-evaluation",
                frozenset({EvidenceChannel.HUMAN_EVALUATION}),
                "human evaluation with outcome, measure, study design, comparator, population, and estimand",
                ClaimType.ANALYST_BENEFIT,
                (
                    "outcome",
                    "measure",
                    "study_design",
                    "comparator",
                    "population",
                    "estimand",
                ),
                True,
            ),
        ),
        object_signatures=((ObjectType.INTERFACE, ObjectType.ANALYST_POPULATION),),
    ),
    ClaimType.SPECIFICATION_PERSISTENCE: ClaimPolicy(
        ClaimType.SPECIFICATION_PERSISTENCE,
        (frozenset({EvidenceChannel.SPECIFICATION_SURFACE}),),
        VisualEncoding.NO_RELATION,
        "The result has the reported descriptive frequency across the declared specification surface.",
        "Evaluate the result across a declared specification surface.",
        object_signatures=((ObjectType.RESULT, ObjectType.SPECIFICATION_SURFACE),),
    ),
    ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE: ClaimPolicy(
        ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE,
        (frozenset({EvidenceChannel.SPECIFICATION_SURFACE}),),
        VisualEncoding.NO_RELATION,
        "The result meets the declared specification-persistence gate.",
        "Measure persistence across the declared surface and meet the declared gate.",
        object_signatures=((ObjectType.RESULT, ObjectType.SPECIFICATION_SURFACE),),
    ),
    ClaimType.BOOTSTRAP_PERSISTENCE: ClaimPolicy(
        ClaimType.BOOTSTRAP_PERSISTENCE,
        (frozenset({EvidenceChannel.CLUSTER_BOOTSTRAP}),),
        VisualEncoding.NO_RELATION,
        "The result has the reported persistence under the declared resampling scheme.",
        "Supply a declared resampling scheme that repeats the extraction pipeline.",
        object_signatures=((ObjectType.RESULT, ObjectType.RESAMPLING_SCHEME),),
    ),
    ClaimType.STATISTICAL_STABILITY: ClaimPolicy(
        ClaimType.STATISTICAL_STABILITY,
        (frozenset({EvidenceChannel.CLUSTER_BOOTSTRAP}),),
        VisualEncoding.NO_RELATION,
        "The result meets the declared cluster-bootstrap stability criterion.",
        "Supply a dependence-aware cluster bootstrap that repeats the extraction pipeline.",
        requires_uncertainty=True,
        requires_independence=True,
        object_signatures=((ObjectType.RESULT, ObjectType.RESAMPLING_SCHEME),),
    ),
}


FALLBACK_PREFERENCES = {
    ClaimType.ASYMMETRIC_CONDITIONAL: (ClaimType.LEXICAL_ASSOCIATION,),
    ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE: (ClaimType.LEXICAL_ASSOCIATION,),
    ClaimType.TEXTUAL_ENTAILMENT: (ClaimType.LEXICAL_ASSOCIATION,),
    ClaimType.EVENT_TEMPORAL_PRECEDENCE: (ClaimType.LEXICAL_ASSOCIATION,),
    ClaimType.CONCEPT_PREREQUISITE: (ClaimType.LEXICAL_ASSOCIATION,),
    ClaimType.CAUSAL_INFLUENCE: (ClaimType.LEXICAL_ASSOCIATION,),
}

FALLBACK_PROJECTIONS = {
    (source_claim, ClaimType.LEXICAL_ASSOCIATION): FallbackProjection(
        "lexicalize-pair-v1",
        source_claim,
        ClaimType.LEXICAL_ASSOCIATION,
        (ObjectType.TERM, ObjectType.TERM),
    )
    for source_claim in FALLBACK_PREFERENCES
}


_CAUSAL_CHANNELS = frozenset(
    {EvidenceChannel.CAUSAL_IDENTIFICATION, EvidenceChannel.INTERVENTION}
)

CLAIM_SCOPE_SEMANTICS = {
    ClaimType.LEXICAL_ASSOCIATION: RelationScope.SYMMETRIC,
    ClaimType.ASYMMETRIC_CONDITIONAL: RelationScope.ORDERED,
    ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE: RelationScope.SYMMETRIC,
    ClaimType.SENTENTIAL_NON_PARAPHRASE: RelationScope.SYMMETRIC,
    ClaimType.CONCEPT_EQUIVALENCE: RelationScope.SYMMETRIC,
    ClaimType.TEXTUAL_ENTAILMENT: RelationScope.ORDERED,
    ClaimType.EVENT_TEMPORAL_PRECEDENCE: RelationScope.ORDERED,
    ClaimType.CONCEPT_PREREQUISITE: RelationScope.ORDERED,
    ClaimType.CAUSAL_INFLUENCE: RelationScope.ORDERED,
    ClaimType.THEME: RelationScope.UNSCOPED,
    ClaimType.ANALYST_BENEFIT: RelationScope.UNSCOPED,
    ClaimType.SPECIFICATION_PERSISTENCE: RelationScope.UNSCOPED,
    ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE: RelationScope.UNSCOPED,
    ClaimType.BOOTSTRAP_PERSISTENCE: RelationScope.UNSCOPED,
    ClaimType.STATISTICAL_STABILITY: RelationScope.UNSCOPED,
}

CLAIM_FAMILIES = {
    ClaimType.LEXICAL_ASSOCIATION: ClaimFamily.OBSERVATIONAL,
    ClaimType.ASYMMETRIC_CONDITIONAL: ClaimFamily.OBSERVATIONAL,
    ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE: ClaimFamily.SEMANTIC_RELATIONAL,
    ClaimType.SENTENTIAL_NON_PARAPHRASE: ClaimFamily.SEMANTIC_RELATIONAL,
    ClaimType.CONCEPT_EQUIVALENCE: ClaimFamily.SEMANTIC_RELATIONAL,
    ClaimType.TEXTUAL_ENTAILMENT: ClaimFamily.SEMANTIC_RELATIONAL,
    ClaimType.EVENT_TEMPORAL_PRECEDENCE: ClaimFamily.SEMANTIC_RELATIONAL,
    ClaimType.CONCEPT_PREREQUISITE: ClaimFamily.SEMANTIC_RELATIONAL,
    ClaimType.CAUSAL_INFLUENCE: ClaimFamily.CAUSAL,
    ClaimType.THEME: ClaimFamily.INTERPRETIVE,
    ClaimType.ANALYST_BENEFIT: ClaimFamily.HUMAN_OUTCOME,
    ClaimType.SPECIFICATION_PERSISTENCE: ClaimFamily.STATISTICAL,
    ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE: ClaimFamily.STATISTICAL,
    ClaimType.BOOTSTRAP_PERSISTENCE: ClaimFamily.STATISTICAL,
    ClaimType.STATISTICAL_STABILITY: ClaimFamily.STATISTICAL,
}

_LEGACY_REQUIRED_ALTERNATIVES = {
    ClaimType.EVENT_TEMPORAL_PRECEDENCE: (
        frozenset({EvidenceChannel.ORDER}),
        frozenset({EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE}),
    ),
    ClaimType.CONCEPT_PREREQUISITE: (
        frozenset({EvidenceChannel.CROSS_REFERENCE}),
        frozenset({EvidenceChannel.ANNOTATION_PREREQUISITE}),
    ),
}


def _policy_predicates(policy: ClaimPolicy) -> tuple[EvidencePredicate, ...]:
    if policy.predicates:
        return policy.predicates
    return tuple(
        EvidencePredicate(
            "construct-matched-support",
            alternative,
            "+".join(sorted(channel.value for channel in alternative)),
            policy.claim_type,
        )
        for alternative in policy.required_alternatives
    )


def _predicates_for_version(
    policy: ClaimPolicy, policy_version: str
) -> tuple[EvidencePredicate, ...]:
    predicates = _policy_predicates(policy)
    if (
        policy.claim_type is ClaimType.CAUSAL_INFLUENCE
        and policy_version not in {"2.6.0", POLICY_VERSION}
    ):
        return tuple(
            replace(predicate, requires_approved_adjudication=False)
            for predicate in predicates
        )
    return predicates


def _record_matches_request(
    record: EvidenceRecord,
    evidence: EvidenceBundle,
    claim_type: ClaimType,
    enforce_relation: bool,
) -> bool:
    if not enforce_relation or evidence.requested_relation is None:
        return True
    scope = CLAIM_SCOPE_SEMANTICS[claim_type]
    if scope is RelationScope.UNSCOPED:
        return True
    if record.relation == evidence.requested_relation:
        return True
    return (
        scope is RelationScope.SYMMETRIC
        and record.relation == tuple(reversed(evidence.requested_relation))
    )


def _bundle_predicate_matches(
    predicate: EvidencePredicate,
    evidence: EvidenceBundle,
    claim_type: ClaimType,
    enforce_relation: bool,
) -> bool:
    """Evaluate one sufficient predicate over all matching records in a bundle."""
    supporting_records = tuple(
        record
        for record in evidence.evidence_records()
        if record.polarity is EvidencePolarity.SUPPORT
        and (record.target is None or record.target is predicate.target)
        and _record_matches_request(record, evidence, claim_type, enforce_relation)
    )
    matched_channels = frozenset(record.channel for record in supporting_records)
    if not predicate.channels <= matched_channels:
        return False
    relevant_records = tuple(
        record for record in supporting_records if record.channel in predicate.channels
    )
    metadata_matches = all(
        any(bool(getattr(record, field)) for record in relevant_records)
        for field in predicate.required_metadata
    )
    adjudication_matches = (
        not predicate.requires_approved_adjudication
        or any(
            record.adjudication_status is AdjudicationStatus.APPROVED
            for record in relevant_records
        )
    )
    return metadata_matches and adjudication_matches


def _object_types_match(
    policy: ClaimPolicy, evidence: EvidenceBundle, policy_version: str
) -> bool:
    if (
        policy_version not in _TYPED_OBJECT_POLICY_VERSIONS
        or evidence.governed_object is None
    ):
        return True
    return evidence.governed_object.signature in policy.object_signatures


def _requirements_for_version(
    policy: ClaimPolicy, policy_version: str
) -> tuple[frozenset[EvidenceChannel], ...]:
    if policy_version in {"2.0.0", "2.1.0"}:
        return _LEGACY_REQUIRED_ALTERNATIVES.get(
            policy.claim_type, policy.required_alternatives
        )
    return policy.required_alternatives


def _is_identifiable(
    policy: ClaimPolicy, evidence: EvidenceBundle, policy_version: str
) -> bool:
    if policy_version in {"2.0.0", "2.1.0"}:
        return any(
            requirement <= evidence.observed_channels
            for requirement in _requirements_for_version(policy, policy_version)
        )
    predicate_matches = any(
        _bundle_predicate_matches(
            predicate,
            evidence,
            policy.claim_type,
            enforce_relation=policy_version in _RELATION_SCOPED_POLICY_VERSIONS,
        )
        for predicate in _predicates_for_version(policy, policy_version)
    )
    if not predicate_matches or not _object_types_match(policy, evidence, policy_version):
        return False
    if policy_version in _ADEQUACY_GATE_POLICY_VERSIONS:
        if policy.claim_type is ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE:
            return (
                evidence.specification_survival is not None
                and evidence.specification_survival >= evidence.minimum_survival
            )
        if policy.claim_type is ClaimType.STATISTICAL_STABILITY:
            return evidence.uncertainty_adequate and evidence.dependence_adequate
    return True


def _requirement_reason_codes(
    policy: ClaimPolicy,
    evidence: EvidenceBundle,
    policy_version: str,
) -> list[ReasonCode]:
    if policy_version in {"2.0.0", "2.1.0"}:
        if not any(
            requirement <= evidence.observed_channels
            for requirement in _requirements_for_version(policy, policy_version)
        ):
            return [ReasonCode.EVIDENCE_CHANNEL_ABSENT]
        return []

    required_alternatives = _requirements_for_version(policy, policy_version)
    all_records = evidence.evidence_records()
    if not any(
        alternative <= evidence.observed_channels
        for alternative in required_alternatives
    ):
        if (
            policy_version == POLICY_VERSION
            and policy.claim_type is ClaimType.EVENT_TEMPORAL_PRECEDENCE
            and EvidenceChannel.MENTION_ORDER in evidence.observed_channels
        ):
            return [ReasonCode.MENTION_ORDER_INSUFFICIENT]
        return [ReasonCode.EVIDENCE_CHANNEL_ABSENT]

    supporting_records = tuple(
        record for record in all_records if record.polarity is EvidencePolarity.SUPPORT
    )
    support_channels = frozenset(record.channel for record in supporting_records)
    if not any(alternative <= support_channels for alternative in required_alternatives):
        return [ReasonCode.SUPPORT_EVIDENCE_ABSENT]

    target_matching_records = tuple(
        record
        for record in supporting_records
        if record.target is None or record.target is policy.claim_type
    )
    target_channels = frozenset(record.channel for record in target_matching_records)
    if not any(alternative <= target_channels for alternative in required_alternatives):
        return [ReasonCode.EVIDENCE_TARGET_MISMATCH]

    enforce_relation = policy_version in _RELATION_SCOPED_POLICY_VERSIONS
    relation_matching_records = tuple(
        record
        for record in target_matching_records
        if _record_matches_request(
            record, evidence, policy.claim_type, enforce_relation
        )
    )
    relation_channels = frozenset(record.channel for record in relation_matching_records)
    if not any(alternative <= relation_channels for alternative in required_alternatives):
        return [ReasonCode.RELATION_SCOPE_MISMATCH]

    if not any(
        _bundle_predicate_matches(
            predicate,
            evidence,
            policy.claim_type,
            enforce_relation=enforce_relation,
        )
        for predicate in _predicates_for_version(policy, policy_version)
    ):
        if any(
            predicate.requires_approved_adjudication
            for predicate in _predicates_for_version(policy, policy_version)
        ) and not any(
            record.adjudication_status is AdjudicationStatus.APPROVED
            for record in relation_matching_records
        ):
            return [ReasonCode.ADJUDICATION_REQUIRED]
        return [ReasonCode.PREDICATE_METADATA_INCOMPLETE]

    reasons: list[ReasonCode] = []
    if not _object_types_match(policy, evidence, policy_version):
        reasons.append(ReasonCode.OBJECT_TYPE_MISMATCH)
    if (
        policy_version in _ADEQUACY_GATE_POLICY_VERSIONS
        and policy.claim_type is ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE
        and (
            evidence.specification_survival is None
            or evidence.specification_survival < evidence.minimum_survival
        )
    ):
        reasons.append(ReasonCode.PERSISTENCE_GATE_FAILED)
    if (
        policy_version in _ADEQUACY_GATE_POLICY_VERSIONS
        and policy.claim_type is ClaimType.STATISTICAL_STABILITY
    ):
        if not evidence.uncertainty_adequate:
            reasons.append(ReasonCode.UNCERTAINTY_INADEQUATE)
        if not evidence.dependence_adequate:
            reasons.append(ReasonCode.DEPENDENCE_INADEQUATE)
    return reasons


def _project_fallback_evidence(
    claim_type: ClaimType,
    candidate: ClaimType,
    evidence: EvidenceBundle,
    policy_version: str,
) -> tuple[EvidenceBundle, FallbackProjection | None, GovernedObject | None, tuple[str, ...]]:
    if policy_version != POLICY_VERSION:
        return evidence, None, evidence.governed_object, ()
    projection = FALLBACK_PROJECTIONS.get((claim_type, candidate))
    if projection is None or not projection.preserves_provenance:
        return evidence, None, None, ()
    if evidence.governed_object is None:
        return evidence, None, None, ()
    lexical_handles: dict[str, str] = {}
    for endpoint, handle in evidence.lexical_handles:
        if not endpoint or not handle:
            return evidence, None, None, ()
        if endpoint in lexical_handles and lexical_handles[endpoint] != handle:
            return evidence, None, None, ()
        lexical_handles[endpoint] = handle
    source_handle = lexical_handles.get(evidence.governed_object.source)
    target_handle = lexical_handles.get(evidence.governed_object.target)
    if source_handle is None or target_handle is None:
        return evidence, None, None, ()
    if not {source_handle, target_handle} <= evidence.represented_terms:
        return evidence, None, None, ()
    if (
        evidence.governed_object.source != evidence.governed_object.target
        and source_handle == target_handle
    ):
        return evidence, None, None, ()
    projected_pair = (source_handle, target_handle)
    reverse_pair = (target_handle, source_handle)
    if (
        EvidenceChannel.CO_OCCURRENCE not in evidence.observed_channels
        or not ({projected_pair, reverse_pair} & evidence.observed_term_pairs)
    ):
        return evidence, None, None, ()
    projected_object = GovernedObject(
        source_handle,
        projection.target_signature[0],
        target_handle,
        projection.target_signature[1],
    )
    projected_evidence = replace(
        evidence,
        governed_object=projected_object,
        requested_relation=(
            projected_object.relation
            if projected_object is not None
            else evidence.requested_relation
        ),
    )
    provenance = (
        (
            f"Canonical lexical handles map {evidence.governed_object.source!r} to "
            f"{source_handle!r} and {evidence.governed_object.target!r} to "
            f"{target_handle!r}."
        ),
        "Both projected handles occur in the represented corpus vocabulary.",
        "The projected pair has independently observed co-occurrence evidence.",
        "Evidence-record and corpus lineage retained from the requested claim bundle.",
    )
    return projected_evidence, projection, projected_object, provenance


def _select_fallback(
    claim_type: ClaimType, evidence: EvidenceBundle, policy_version: str
) -> tuple[
    ClaimType | None,
    FallbackProjection | None,
    GovernedObject | None,
    tuple[str, ...],
    ClaimCertificate | None,
]:
    for candidate in FALLBACK_PREFERENCES.get(claim_type, ()):
        projected_evidence, projection, projected_object, provenance = (
            _project_fallback_evidence(
                claim_type, candidate, evidence, policy_version
            )
        )
        if policy_version == POLICY_VERSION and projection is None:
            continue
        candidate_certificate = evaluate_claim(
            candidate, projected_evidence, policy_version
        )
        if candidate_certificate.policy_admissible:
            return (
                candidate,
                projection,
                projected_object,
                provenance,
                candidate_certificate,
            )
    return None, None, None, (), None


def evaluate_claim(
    claim_type: ClaimType,
    evidence: EvidenceBundle,
    policy_version: str = POLICY_VERSION,
) -> ClaimCertificate:
    """Apply a lexicographic policy; later checks cannot rescue identifiability."""
    if policy_version not in SUPPORTED_POLICY_VERSIONS:
        raise ValueError(f"Unsupported policy version: {policy_version}")
    policy = POLICIES[claim_type]
    required_alternatives = _requirements_for_version(policy, policy_version)
    required_predicates = _predicates_for_version(policy, policy_version)
    observational_identifiability = None
    if EvidenceChannel.CO_OCCURRENCE in evidence.observed_channels:
        observational_identifiability = claim_type in {
            ClaimType.LEXICAL_ASSOCIATION,
            ClaimType.ASYMMETRIC_CONDITIONAL,
        }
    identifiable = _is_identifiable(policy, evidence, policy_version)
    reason_codes = _requirement_reason_codes(policy, evidence, policy_version)
    object_type_match = _object_types_match(policy, evidence, policy_version)
    adjudication_required = any(
        predicate.requires_approved_adjudication
        for predicate in required_predicates
    )
    adjudication_approved = any(
        record.adjudication_status is AdjudicationStatus.APPROVED
        and (record.target is None or record.target is claim_type)
        for record in evidence.evidence_records()
    )
    witness: list[str] = []
    remediation: list[str] = []
    refusal_class: RefusalClass | None = None
    has_construct_conflict = False

    if not identifiable:
        decision = Decision.REFUSE
        refusal_class = (
            RefusalClass.POLICY
            if any(
                reason
                in {
                    ReasonCode.ADJUDICATION_REQUIRED,
                    ReasonCode.PERSISTENCE_GATE_FAILED,
                    ReasonCode.UNCERTAINTY_INADEQUATE,
                    ReasonCode.DEPENDENCE_INADEQUATE,
                }
                for reason in reason_codes
            )
            else RefusalClass.EPISTEMIC
        )
        if ReasonCode.EVIDENCE_CHANNEL_ABSENT in reason_codes:
            missing = [
                "+".join(sorted(channel.value for channel in alternative))
                for alternative in required_alternatives
            ]
            witness.append(
                "Missing required evidence alternative: " + " OR ".join(missing) + "."
            )
        elif ReasonCode.SUPPORT_EVIDENCE_ABSENT in reason_codes:
            witness.append("The required channel is present, but no supporting record matches it.")
        elif ReasonCode.EVIDENCE_TARGET_MISMATCH in reason_codes:
            witness.append("The required channel is present, but its claim target does not match.")
        elif ReasonCode.RELATION_SCOPE_MISMATCH in reason_codes:
            witness.append("The required channel is present, but its relation or scope does not match.")
        elif ReasonCode.ADJUDICATION_REQUIRED in reason_codes:
            witness.append("Required evidence is present but lacks approved adjudication.")
        elif ReasonCode.PREDICATE_METADATA_INCOMPLETE in reason_codes:
            witness.append("Required evidence is present but predicate metadata is incomplete.")
        if not object_type_match:
            witness.append("The governed object types do not match the requested claim.")
        if (
            claim_type is ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE
            and evidence.specification_survival is not None
            and evidence.specification_survival < evidence.minimum_survival
        ):
            witness.append(
                f"The observed persistence S={evidence.specification_survival:.3f} "
                f"does not meet gate={evidence.minimum_survival:.3f}."
            )
        if claim_type is ClaimType.STATISTICAL_STABILITY:
            if not evidence.uncertainty_adequate:
                witness.append("Uncertainty evidence is inadequate for identification.")
            if not evidence.dependence_adequate:
                witness.append("Dependence-aware resampling is not established.")
        if evidence.counterevidence:
            witness.append(
                "Explicit counterevidence is recorded but does not substitute for the "
                "missing identifying channel: " + "; ".join(evidence.counterevidence)
            )
        remediation.append(policy.remediation)
    elif not evidence.provenance_complete:
        decision = Decision.REFUSE
        reason_codes.append(ReasonCode.PROVENANCE_INCOMPLETE)
        refusal_class = RefusalClass.OPERATIONAL
        witness.append("Required provenance fields are incomplete for the intended claim.")
        remediation.append("Complete the claim policy's required lineage fields.")
    elif (
        claim_type is ClaimType.CAUSAL_INFLUENCE
        and policy_version == "2.1.0"
        and (
            not evidence.causal_method
            or not evidence.causal_assumptions
            or not evidence.causal_estimand
        )
    ):
        decision = Decision.REFUSE
        witness.append(
            "The causal-identification channel lacks a declared method, assumptions, "
            "or estimand."
        )
        remediation.append(
            "Declare the identification method, assumptions, and target estimand."
        )
    else:
        qualification_reasons = []
        decision: Decision | None = None
        if policy.force_qualification:
            qualification_reasons.append(policy.force_qualification)
            reason_codes.append(ReasonCode.PREVALENCE_QUALIFICATION)
        if (
            evidence.specification_survival is not None
            and evidence.specification_survival < evidence.minimum_survival
            and claim_type
            not in {
                ClaimType.SPECIFICATION_PERSISTENCE,
                ClaimType.MEETS_SPECIFICATION_PERSISTENCE_GATE,
            }
        ):
            if evidence.specification_survival < evidence.minimum_survival / 2:
                persistence_reason = "highly specification-sensitive"
            elif evidence.minimum_survival - evidence.specification_survival <= 0.05:
                persistence_reason = "near-threshold persistence"
            else:
                persistence_reason = "below-threshold persistence"
            qualification_reasons.append(
                f"{persistence_reason}: S={evidence.specification_survival:.3f}; "
                f"gate={evidence.minimum_survival:.3f}."
            )
            reason_codes.append(ReasonCode.PERSISTENCE_QUALIFICATION)
        if policy.requires_uncertainty and not evidence.uncertainty_adequate:
            qualification_reasons.append("Uncertainty evidence is inadequate for admission.")
        if policy.requires_independence and not evidence.dependence_adequate:
            qualification_reasons.append(
                "Supporting units are not established as independent evidence sources."
            )
        matched_records = tuple(
            record
            for record in evidence.evidence_records()
            if (record.target is None or record.target is claim_type)
            and _record_matches_request(
                record,
                evidence,
                claim_type,
                enforce_relation=policy_version in _RELATION_SCOPED_POLICY_VERSIONS,
            )
        )
        record_support = tuple(
            record
            for record in matched_records
            if record.polarity is EvidencePolarity.SUPPORT
        )
        record_counterevidence = tuple(
            record
            for record in matched_records
            if record.polarity is EvidencePolarity.COUNTEREVIDENCE
        )
        if record_counterevidence:
            has_construct_conflict = True
            reason_codes.append(ReasonCode.CONFLICT_PRESENT)
            qualification_reasons.append(
                "Construct-matched conflict: support: "
                + "; ".join(
                    record.source or record.channel.value for record in record_support
                )
                + "; counterevidence: "
                + "; ".join(
                    record.source or record.channel.value
                    for record in record_counterevidence
                )
                + "."
            )
        if evidence.counterevidence:
            qualification_reasons.append(
                "Explicit counterevidence is present: " + "; ".join(evidence.counterevidence)
            )
        if decision is None and qualification_reasons:
            decision = Decision.QUALIFY
            witness.extend(qualification_reasons)
            remediation.append("Inspect sensitivity and uncertainty before using the claim.")
        elif decision is None:
            decision = Decision.ADMIT

    fallback_claim = None
    fallback_decision = None
    fallback_allowed_export = None
    fallback_projection = None
    fallback_projected_object = None
    fallback_projection_provenance: tuple[str, ...] = ()
    allowed_encoding = policy.allowed_encoding
    allowed_statement = policy.allowed_statement
    allowed_export = (
        decision is not Decision.REFUSE or policy.allow_refused_export
    )
    requested_representation_authorized = decision is not Decision.REFUSE
    if decision is Decision.QUALIFY and has_construct_conflict:
        allowed_encoding = VisualEncoding.CONTESTED_RELATION
        allowed_statement = (
            "Construct-matched support and counterevidence contest this relation."
        )
        allowed_export = False
    if decision is Decision.REFUSE:
        requested_representation_authorized = False
        (
            fallback_claim,
            projection,
            fallback_projected_object,
            fallback_projection_provenance,
            fallback_certificate,
        ) = _select_fallback(claim_type, evidence, policy_version)
        fallback_projection = projection.projection_id if projection is not None else None
        if fallback_certificate is not None:
            fallback_decision = fallback_certificate.decision
            fallback_allowed_export = fallback_certificate.allowed_export
            allowed_encoding = fallback_certificate.allowed_encoding
            allowed_statement = fallback_certificate.allowed_statement
        else:
            allowed_encoding = VisualEncoding.NO_RELATION
            allowed_statement = "No relation claim is exportable from the available evidence."

    triggered_reasons = tuple(dict.fromkeys(reason_codes))
    if decision is not Decision.ADMIT and not triggered_reasons:
        triggered_reasons = (ReasonCode.PREDICATE_METADATA_INCOMPLETE,)
    if decision is Decision.ADMIT:
        decision_reason = None
        if not witness:
            witness.append("All required evidence and policy gates passed.")
    elif has_construct_conflict:
        decision_reason = ReasonCode.CONFLICT_PRESENT
    else:
        decision_reason = triggered_reasons[0]

    return ClaimCertificate(
        policy_version=policy_version,
        claim_type=claim_type,
        claim_family=CLAIM_FAMILIES[claim_type],
        requested_relation=evidence.requested_relation,
        governed_object=evidence.governed_object,
        required_object_signatures=policy.object_signatures,
        object_type_match=object_type_match,
        adjudication_required=adjudication_required,
        adjudication_approved=adjudication_approved,
        required_alternatives=required_alternatives,
        required_predicates=required_predicates,
        observed_channels=evidence.observed_channels,
        observational_identifiability=observational_identifiability,
        identifiable=identifiable,
        policy_admissible=decision is not Decision.REFUSE,
        reason_codes=triggered_reasons,
        triggered_reasons=triggered_reasons,
        decision_reason=decision_reason,
        refusal_class=refusal_class,
        provenance_complete=evidence.provenance_complete,
        specification_survival=evidence.specification_survival,
        uncertainty_adequate=evidence.uncertainty_adequate,
        dependence_adequate=evidence.dependence_adequate,
        counterevidence=evidence.counterevidence,
        causal_method=evidence.causal_method,
        causal_assumptions=evidence.causal_assumptions,
        causal_estimand=evidence.causal_estimand,
        causal_design=evidence.causal_design,
        causal_diagnostics=evidence.causal_diagnostics,
        decision=decision,
        allowed_encoding=allowed_encoding,
        allowed_statement=allowed_statement,
        allowed_export=allowed_export,
        requested_representation_authorized=requested_representation_authorized,
        fallback_claim=fallback_claim,
        fallback_decision=fallback_decision,
        fallback_allowed_export=fallback_allowed_export,
        fallback_is_policy_preferred=fallback_claim is not None,
        fallback_projection=fallback_projection,
        fallback_projected_object=fallback_projected_object,
        fallback_projection_provenance=fallback_projection_provenance,
        witness=tuple(witness),
        remediation=tuple(remediation),
    )


def evaluate_all_claims(evidence: EvidenceBundle) -> list[ClaimCertificate]:
    """Evaluate every claim in stable policy order for serialization and interfaces."""
    return [evaluate_claim(claim_type, evidence) for claim_type in ClaimType]
    
def policy_as_dict() -> dict[str, Any]:
    """Serialize the active policy as a declarative, machine-auditable artifact."""
    claims = []
    for claim_type, policy in POLICIES.items():
        claims.append(
            {
                "claim": claim_type.value,
                "claim_family": CLAIM_FAMILIES[claim_type].value,
                "scope_semantics": CLAIM_SCOPE_SEMANTICS[claim_type].value,
                "object_signatures": [
                    [source_type.value, target_type.value]
                    for source_type, target_type in policy.object_signatures
                ],
                "evidence_predicates": [
                    {
                        "predicate_id": predicate.predicate_id,
                        "channels": sorted(
                            channel.value for channel in predicate.channels
                        ),
                        "target": (
                            predicate.target.value if predicate.target else None
                        ),
                        "required_metadata": list(predicate.required_metadata),
                        "requires_approved_adjudication": (
                            predicate.requires_approved_adjudication
                        ),
                        "description": predicate.description,
                    }
                    for predicate in _policy_predicates(policy)
                ],
                "encoding": policy.allowed_encoding.value,
                "statement": policy.allowed_statement,
                "remediation": policy.remediation,
                "on_counterevidence": "qualify-conflict-when-support-matches",
                "fallback_preferences": [
                    candidate.value
                    for candidate in FALLBACK_PREFERENCES.get(claim_type, ())
                ],
                "fallback_projections": [
                    {
                        "target_claim": candidate.value,
                        "projection_id": FALLBACK_PROJECTIONS[
                            (claim_type, candidate)
                        ].projection_id,
                        "target_signature": [
                            object_type.value
                            for object_type in FALLBACK_PROJECTIONS[
                                (claim_type, candidate)
                            ].target_signature
                        ],
                        "preserves_labels": FALLBACK_PROJECTIONS[
                            (claim_type, candidate)
                        ].preserves_labels,
                        "preserves_provenance": FALLBACK_PROJECTIONS[
                            (claim_type, candidate)
                        ].preserves_provenance,
                        "defined_when": [
                            "each endpoint has one canonical lexical handle",
                            "both handles occur in the represented corpus vocabulary",
                            "distinct endpoints do not collapse to one handle",
                            "the projected pair has independently observed co-occurrence",
                        ],
                        "undefined_consequence": "no-relation",
                    }
                    for candidate in FALLBACK_PREFERENCES.get(claim_type, ())
                ],
                "requires_uncertainty": policy.requires_uncertainty,
                "requires_independence": policy.requires_independence,
                "refused_export_blocked": not policy.allow_refused_export,
            }
        )
    return {
        "schema_version": "1.0",
        "policy_version": POLICY_VERSION,
        "decision_order": [
            "evidence-and-policy-admissibility",
            "provenance",
            "qualification-and-conflict-gates",
        ],
        "decisions": [decision.value for decision in Decision],
        "claims": claims,
    }

def lint_policy(
    policies: dict[ClaimType, ClaimPolicy] | None = None,
    fallback_preferences: dict[ClaimType, tuple[ClaimType, ...]] | None = None,
    fallback_projections: dict[
        tuple[ClaimType, ClaimType], FallbackProjection
    ] | None = None,
    active_version: str = POLICY_VERSION,
) -> dict[str, Any]:
    """Mechanically audit active policy structure and selected behavior invariants."""
    candidate_policies = POLICIES if policies is None else policies
    candidate_fallbacks = (
        FALLBACK_PREFERENCES
        if fallback_preferences is None
        else fallback_preferences
    )
    candidate_projections = (
        FALLBACK_PROJECTIONS
        if fallback_projections is None
        else fallback_projections
    )
    predicate_keys = {
        claim_type: [
            (
                predicate.predicate_id,
                tuple(sorted(channel.value for channel in predicate.channels)),
                predicate.required_metadata,
            )
            for predicate in _policy_predicates(policy)
        ]
        for claim_type, policy in candidate_policies.items()
    }

    def fallback_graph_is_acyclic() -> bool:
        visiting: set[ClaimType] = set()
        visited: set[ClaimType] = set()

        def visit(claim_type: ClaimType) -> bool:
            if claim_type in visiting:
                return False
            if claim_type in visited:
                return True
            visiting.add(claim_type)
            if not all(
                visit(candidate)
                for candidate in candidate_fallbacks.get(claim_type, ())
            ):
                return False
            visiting.remove(claim_type)
            visited.add(claim_type)
            return True

        return all(visit(claim_type) for claim_type in candidate_policies)

    causal_metadata = {
        "method",
        "assumptions",
        "estimand",
        "study_design",
        "diagnostics",
    }
    interpretive_metadata = {
        ClaimType.THEME: {
            "method",
            "analytic_traceability",
            "reflexive_documentation",
            "theory_alignment",
        },
        ClaimType.ANALYST_BENEFIT: {
            "outcome",
            "measure",
            "study_design",
            "comparator",
            "population",
            "estimand",
        },
    }
    checks = {
        "all_claims_declared": set(candidate_policies) == set(ClaimType),
        "requirements_reachable": all(
            all(predicate.channels for predicate in _policy_predicates(policy))
            for policy in candidate_policies.values()
        ),
        "no_duplicate_predicates": all(
            len(keys) == len(set(keys)) for keys in predicate_keys.values()
        ),
        "remediation_complete": all(
            bool(policy.remediation.strip()) for policy in candidate_policies.values()
        ),
        "construct_specific_order": EvidenceChannel.ORDER
        not in {
            channel
            for alternative in candidate_policies[
                ClaimType.EVENT_TEMPORAL_PRECEDENCE
            ].required_alternatives
            for channel in alternative
        },
        "construct_specific_reference": EvidenceChannel.CROSS_REFERENCE
        not in {
            channel
            for alternative in candidate_policies[
                ClaimType.CONCEPT_PREREQUISITE
            ].required_alternatives
            for channel in alternative
        },
        "causal_metadata_consistent": all(
            set(predicate.required_metadata) == causal_metadata
            for predicate in _policy_predicates(
                candidate_policies[ClaimType.CAUSAL_INFLUENCE]
            )
        ),
        "object_signatures_complete": all(
            bool(policy.object_signatures)
            for policy in candidate_policies.values()
        ),
        "interpretive_adjudication_required": all(
            claim_type in candidate_policies
            and all(
                predicate.requires_approved_adjudication
                for predicate in _policy_predicates(
                    candidate_policies[claim_type]
                )
            )
            for claim_type in (ClaimType.THEME, ClaimType.ANALYST_BENEFIT)
        ),
        "causal_adjudication_required": all(
            predicate.requires_approved_adjudication
            for predicate in _policy_predicates(
                candidate_policies[ClaimType.CAUSAL_INFLUENCE]
            )
        ),
        "causal_identification_not_intervention_alternative": (
            ClaimType.CAUSAL_INFLUENCE in candidate_policies
            and candidate_policies[
                ClaimType.CAUSAL_INFLUENCE
            ].required_alternatives
            == (frozenset({EvidenceChannel.CAUSAL_IDENTIFICATION}),)
        ),
        "fallback_targets_declared": all(
            candidate in candidate_policies
            for candidates in candidate_fallbacks.values()
            for candidate in candidates
        ),
        "fallback_graph_acyclic": fallback_graph_is_acyclic(),
        "fallback_scope_compatible": all(
            CLAIM_SCOPE_SEMANTICS[source] is not RelationScope.UNSCOPED
            or CLAIM_SCOPE_SEMANTICS[candidate] is RelationScope.UNSCOPED
            for source, candidates in candidate_fallbacks.items()
            for candidate in candidates
        ),
        "fallback_projections_complete": all(
            (source, candidate) in candidate_projections
            for source, candidates in candidate_fallbacks.items()
            for candidate in candidates
        ),
        "fallback_projection_target_compatible": all(
            (source, candidate) not in candidate_projections
            or candidate not in candidate_policies
            or candidate_projections[(source, candidate)].target_signature
            in candidate_policies[candidate].object_signatures
            for source, candidates in candidate_fallbacks.items()
            for candidate in candidates
        ),
        "fallback_projection_provenance_preserved": all(
            (source, candidate) not in candidate_projections
            or candidate_projections[(source, candidate)].preserves_provenance
            for source, candidates in candidate_fallbacks.items()
            for candidate in candidates
        ),
        "refused_exports_blocked": all(
            not policy.allow_refused_export
            for policy in candidate_policies.values()
        ),
        "encoding_semantic_separation": (
            candidate_policies[ClaimType.ASYMMETRIC_CONDITIONAL].allowed_encoding
            is VisualEncoding.CONDITIONAL_ASYMMETRY_GLYPH
            and candidate_policies[ClaimType.ASYMMETRIC_CONDITIONAL].allowed_encoding
            is not candidate_policies[ClaimType.EVENT_TEMPORAL_PRECEDENCE].allowed_encoding
        ),
        "interpretive_metadata_consistent": all(
            claim_type not in candidate_policies
            or all(
                set(predicate.required_metadata) == required_metadata
                for predicate in _policy_predicates(candidate_policies[claim_type])
            )
            for claim_type, required_metadata in interpretive_metadata.items()
        ),
        "declared_semantic_change_witnessed": (
            evaluate_claim(
                ClaimType.CONCEPT_PREREQUISITE,
                EvidenceBundle(frozenset({EvidenceChannel.CROSS_REFERENCE})),
                policy_version="2.1.0",
            ).decision
            is Decision.ADMIT
            and evaluate_claim(
                ClaimType.CONCEPT_PREREQUISITE,
                EvidenceBundle(frozenset({EvidenceChannel.CROSS_REFERENCE})),
                policy_version=active_version,
            ).decision
            is Decision.REFUSE
        ),
    }
    return {
        "policy_version": active_version,
        "check_count": len(checks),
        "passed_count": sum(checks.values()),
        "all_passed": all(checks.values()),
        "checks": checks,
        "issues": [name for name, passed in checks.items() if not passed],
        "scope": (
            "Static and behavioral policy linting establishes internal consistency, "
            "not normative validity."
        ),
    }