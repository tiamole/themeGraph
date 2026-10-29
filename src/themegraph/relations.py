"""Typed asymmetric relation extraction with source evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations

from themegraph.models import EvidenceRecord, RelationEdge, TextUnit


@dataclass(frozen=True, slots=True)
class ConditionalAssociationExtractor:
    """Create A -> B when B is reliably observed in units containing A.

    Confidence is P(B|A), which is asymmetric because source prevalence is the
    denominator. Lift guards against edges caused only by a common target.
    """

    min_term_units: int = 3
    min_pair_units: int = 2
    min_confidence: float = 0.65
    min_lift: float = 1.05
    max_vocabulary: int = 500
    evidence_limit: int = 3

    def extract(self, units: list[TextUnit]) -> tuple[set[str], list[RelationEdge]]:
        term_frequency = Counter(term for unit in units for term in unit.terms)
        eligible = [
            term
            for term, count in term_frequency.most_common()
            if count >= self.min_term_units
        ][: self.max_vocabulary]
        vocabulary = set(eligible)
        pair_frequency: Counter[tuple[str, str]] = Counter()
        pair_evidence: dict[tuple[str, str], list[EvidenceRecord]] = defaultdict(list)
        pair_documents: dict[tuple[str, str], set[str]] = defaultdict(set)
        pair_sources: dict[tuple[str, str], set[str]] = defaultdict(set)

        for unit in units:
            terms = sorted(unit.terms & vocabulary)
            for left, right in combinations(terms, 2):
                pair = (left, right)
                pair_frequency[pair] += 1
                pair_documents[pair].add(unit.document_id)
                if unit.provenance_source:
                    pair_sources[pair].add(unit.provenance_source)
                if len(pair_evidence[pair]) < self.evidence_limit:
                    pair_evidence[pair].append(
                        EvidenceRecord(unit.unit_id, unit.document_id, unit.text[:500])
                    )

        unit_count = max(len(units), 1)
        edges: list[RelationEdge] = []
        for pair, support in sorted(pair_frequency.items()):
            if support < self.min_pair_units:
                continue
            left, right = pair
            document_support = len(pair_documents[pair])
            source_support = len(pair_sources[pair])
            effective_support_lower_bound = min(
                support, document_support, source_support
            )
            for source, target in ((left, right), (right, left)):
                confidence = support / term_frequency[source]
                target_prevalence = term_frequency[target] / unit_count
                lift = confidence / target_prevalence if target_prevalence else 0.0
                if confidence >= self.min_confidence and lift >= self.min_lift:
                    edges.append(
                        RelationEdge(
                            source=source,
                            target=target,
                            relation_type="conditional-association",
                            confidence=confidence,
                            support=support,
                            lift=lift,
                            document_support=document_support,
                            source_support=source_support,
                            effective_support_lower_bound=effective_support_lower_bound,
                            evidence=tuple(pair_evidence[pair]),
                        )
                    )
        return vocabulary, edges
