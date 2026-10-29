"""Bounded specification surfaces and claim-survival summaries."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from statistics import mean
from typing import Any

import networkx as nx

from themegraph.admissibility import (
    ClaimType,
    EvidenceBundle,
    EvidenceChannel,
    evaluate_claim,
)
from themegraph.evaluation import structural_metrics
from themegraph.models import DocumentRecord
from themegraph.pipeline import analyze_documents
from themegraph.relations import ConditionalAssociationExtractor
from themegraph.text import RegexUnitExtractor


@dataclass(frozen=True, slots=True)
class Specification:
    unit_mode: str = "sentence"
    include_bigrams: bool = True
    max_terms_per_unit: int = 30
    max_vocabulary: int = 500
    min_term_units: int = 3
    min_pair_units: int = 2
    min_confidence: float = 0.65
    min_lift: float = 1.05
    exact_deduplication: bool = False

    @property
    def identifier(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def specification_grid(include_bigrams: bool = True) -> tuple[Specification, ...]:
    baseline = Specification(include_bigrams=include_bigrams)
    variants = [baseline]
    axes = {
        "unit_mode": ("sentence", "paragraph", "sentence-window"),
        "include_bigrams": (False, True),
        "max_terms_per_unit": (20, 30, 50),
        "max_vocabulary": (100, 250, 500, 1000),
        "min_term_units": (2, 3, 5),
        "min_pair_units": (1, 2, 3),
        "min_confidence": (0.5, 0.65, 0.8),
        "min_lift": (1.0, 1.05, 1.25),
        "exact_deduplication": (False, True),
    }
    for field, values in axes.items():
        for value in values:
            variants.append(replace(baseline, **{field: value}))
    unique = {specification.identifier: specification for specification in variants}
    return tuple(unique[key] for key in sorted(unique))


def interaction_grid(include_bigrams: bool = True) -> tuple[Specification, ...]:
    baseline = Specification(include_bigrams=include_bigrams)
    variants = (
        replace(baseline, unit_mode="paragraph", max_terms_per_unit=20),
        replace(baseline, unit_mode="sentence-window", max_terms_per_unit=50),
        replace(
            baseline,
            include_bigrams=not include_bigrams,
            max_vocabulary=250,
        ),
        replace(baseline, min_term_units=5, min_pair_units=3),
        replace(baseline, min_confidence=0.8, min_lift=1.25),
        replace(baseline, exact_deduplication=True, min_pair_units=3),
    )
    one_factor_ids = {item.identifier for item in specification_grid(include_bigrams)}
    unique = {
        specification.identifier: specification
        for specification in variants
        if specification.identifier not in one_factor_ids
    }
    return tuple(unique[key] for key in sorted(unique))


def deduplicate_documents(documents: list[DocumentRecord]) -> list[DocumentRecord]:
    observed = set()
    retained = []
    for document in documents:
        normalized = " ".join(document.text.split())
        if normalized in observed:
            continue
        observed.add(normalized)
        retained.append(document)
    return retained


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def _jaccard(first: set[Any], second: set[Any]) -> float:
    union = first | second
    return len(first & second) / len(union) if union else 1.0


def _set_geometry(
    baseline: set[Any], observed_sets: list[set[Any]]
) -> dict[str, Any]:
    union = set().union(*observed_sets)
    intersection = set.intersection(*observed_sets) if observed_sets else set()
    jaccards = [_jaccard(baseline, observed) for observed in observed_sets]
    return {
        "baseline_count": len(baseline),
        "union_count": len(union),
        "intersection_count": len(intersection),
        "emergent_count": len(union - baseline),
        "baseline_jaccard": {
            "minimum": min(jaccards, default=1.0),
            "mean": mean(jaccards) if jaccards else 1.0,
            "median": _percentile(jaccards, 0.5),
            "maximum": max(jaccards, default=1.0),
        },
    }


def _component_overlap(
    baseline_components: set[tuple[str, ...]],
    component_sets: list[set[tuple[str, ...]]],
) -> dict[str, float]:
    ordered_baseline = sorted(baseline_components)
    scores = {baseline: [] for baseline in ordered_baseline}
    for components in component_sets:
        ordered_observed = sorted(components)
        graph = nx.Graph()
        baseline_nodes = [("baseline", index) for index in range(len(ordered_baseline))]
        observed_nodes = [("observed", index) for index in range(len(ordered_observed))]
        graph.add_nodes_from(baseline_nodes, bipartite=0)
        graph.add_nodes_from(observed_nodes, bipartite=1)
        for baseline_index, baseline in enumerate(ordered_baseline):
            for observed_index, observed in enumerate(ordered_observed):
                overlap = _jaccard(set(baseline), set(observed))
                if overlap > 0:
                    graph.add_edge(
                        ("baseline", baseline_index),
                        ("observed", observed_index),
                        weight=overlap,
                    )
        matching = nx.max_weight_matching(graph, weight="weight")
        matched_scores = {baseline: 0.0 for baseline in ordered_baseline}
        for first, second in matching:
            baseline_node, observed_node = (
                (first, second) if first[0] == "baseline" else (second, first)
            )
            baseline = ordered_baseline[baseline_node[1]]
            observed = ordered_observed[observed_node[1]]
            matched_scores[baseline] = _jaccard(set(baseline), set(observed))
        for baseline in ordered_baseline:
            scores[baseline].append(matched_scores[baseline])
    return {
        "|".join(baseline): mean(values) if values else 0.0
        for baseline, values in scores.items()
    }


def _gate_frontier(
    edge_survival: dict[str, float], universe: str
) -> list[dict[str, Any]]:
    return [
        {
            "survival_gate": gate,
            "edge_universe": universe,
            f"admitted_{universe}_edges": sum(
                survival >= gate for survival in edge_survival.values()
            ),
            f"qualified_{universe}_edges": sum(
                survival < gate for survival in edge_survival.values()
            ),
        }
        for gate in (0.5, 2 / 3, 0.75, 0.8, 0.9, 1.0)
    ]


def evaluate_specification_surface(
    documents: list[DocumentRecord],
    corpus_name: str,
    include_bigrams: bool = True,
) -> dict[str, Any]:
    one_factor_configurations = specification_grid(include_bigrams)
    interaction_configurations = interaction_grid(include_bigrams)
    configurations = one_factor_configurations + interaction_configurations
    design_by_id = {
        specification.identifier: "one-factor"
        for specification in one_factor_configurations
    } | {
        specification.identifier: "bounded-two-factor"
        for specification in interaction_configurations
    }
    results = []
    edge_sets: list[set[tuple[str, str]]] = []
    component_sets: list[set[tuple[str, ...]]] = []
    baseline_edges: set[tuple[str, str]] = set()
    baseline_components: set[tuple[str, ...]] = set()
    for specification in configurations:
        selected_documents = (
            deduplicate_documents(documents)
            if specification.exact_deduplication
            else documents
        )
        result = analyze_documents(
            selected_documents,
            corpus_name,
            RegexUnitExtractor(
                unit_mode=specification.unit_mode,
                include_bigrams=specification.include_bigrams,
                max_terms_per_unit=specification.max_terms_per_unit,
            ),
            ConditionalAssociationExtractor(
                min_term_units=specification.min_term_units,
                min_pair_units=specification.min_pair_units,
                min_confidence=specification.min_confidence,
                min_lift=specification.min_lift,
                max_vocabulary=specification.max_vocabulary,
            ),
        )
        edges = {(edge.source, edge.target) for edge in result.edges}
        components = {
            tuple(sorted(component)) for component in result.components if len(component) > 1
        }
        edge_sets.append(edges)
        component_sets.append(components)
        if specification == Specification(include_bigrams=include_bigrams):
            baseline_edges = edges
            baseline_components = components
        results.append(
            {
                "configuration_id": specification.identifier,
                "design": design_by_id[specification.identifier],
                "specification": asdict(specification),
                "documents": len(selected_documents),
                "edge_jaccard_baseline": _jaccard(baseline_edges, edges),
                "component_jaccard_baseline": _jaccard(
                    baseline_components, components
                ),
                **structural_metrics(result),
            }
        )

    for result, edges, components in zip(
        results, edge_sets, component_sets, strict=True
    ):
        result["edge_jaccard_baseline"] = _jaccard(baseline_edges, edges)
        result["component_jaccard_baseline"] = _jaccard(
            baseline_components, components
        )

    configuration_count = len(configurations)
    union_edges = set().union(*edge_sets)
    edge_survival = {
        f"{edge[0]}->{edge[1]}": sum(edge in edges for edges in edge_sets)
        / configuration_count
        for edge in sorted(union_edges)
    }
    default_edge_survival = {
        f"{edge[0]}->{edge[1]}": sum(edge in edges for edges in edge_sets)
        / configuration_count
        for edge in sorted(baseline_edges)
    }
    component_survival = {
        "|".join(component): sum(component in components for components in component_sets)
        / configuration_count
        for component in sorted(baseline_components)
    }
    edge_values = list(edge_survival.values())
    default_edge_values = list(default_edge_survival.values())
    component_values = list(component_survival.values())
    component_overlap = _component_overlap(baseline_components, component_sets)
    component_overlap_values = list(component_overlap.values())
    edge_certificates = [
        evaluate_claim(
            ClaimType.LEXICAL_ASSOCIATION,
            EvidenceBundle(
                frozenset({EvidenceChannel.CO_OCCURRENCE}),
                specification_survival=survival,
            ),
        )
        for survival in edge_values
    ]
    default_edge_certificates = [
        evaluate_claim(
            ClaimType.LEXICAL_ASSOCIATION,
            EvidenceBundle(
                frozenset({EvidenceChannel.CO_OCCURRENCE}),
                specification_survival=survival,
            ),
        )
        for survival in default_edge_values
    ]
    return {
        "corpus_name": corpus_name,
        "surface_type": (
            "unweighted one-factor-at-a-time plus bounded two-factor descriptive surface"
        ),
        "configuration_count": configuration_count,
        "one_factor_configuration_count": len(one_factor_configurations),
        "bounded_interaction_configuration_count": len(interaction_configurations),
        "axes": {
            "unitization": ["sentence", "paragraph", "sentence-window"],
            "token_features": ["unigrams", "unigrams-and-bigrams"],
            "max_terms_per_unit": [20, 30, 50],
            "max_vocabulary": [100, 250, 500, 1000],
            "min_term_units": [2, 3, 5],
            "min_pair_units": [1, 2, 3],
            "min_confidence": [0.5, 0.65, 0.8],
            "min_lift": [1.0, 1.05, 1.25],
            "exact_deduplication": [False, True],
        },
        "unevaluated_axes": [
            "stemming-versus-lemmatization",
            "domain-stopword policies",
            "near-duplicate removal",
            "evidence-sampling policy",
            "exhaustive Cartesian interactions",
            "configuration weighting",
        ],
        "baseline_edge_count": len(baseline_edges),
        "union_edge_count": len(union_edges),
        "baseline_nontrivial_component_count": len(baseline_components),
        "edge_set_geometry": _set_geometry(baseline_edges, edge_sets),
        "component_set_geometry": _set_geometry(
            baseline_components, component_sets
        ),
        "edge_survival": edge_survival,
        "default_edge_survival": default_edge_survival,
        "component_survival": component_survival,
        "component_one_to_one_jaccard": component_overlap,
        "component_matching": "maximum-weight one-to-one bipartite matching per configuration",
        "survival_summary": {
            "edge_minimum": min(edge_values, default=0.0),
            "edge_mean": mean(edge_values) if edge_values else 0.0,
            "edge_p25": _percentile(edge_values, 0.25),
            "edge_median": _percentile(edge_values, 0.5),
            "edge_p75": _percentile(edge_values, 0.75),
            "default_edge_minimum": min(default_edge_values, default=0.0),
            "default_edge_mean": (
                mean(default_edge_values) if default_edge_values else 0.0
            ),
            "default_edge_p25": _percentile(default_edge_values, 0.25),
            "default_edge_median": _percentile(default_edge_values, 0.5),
            "default_edge_p75": _percentile(default_edge_values, 0.75),
            "component_minimum": min(component_values, default=0.0),
            "component_mean": mean(component_values) if component_values else 0.0,
            "component_overlap_minimum": min(
                component_overlap_values, default=0.0
            ),
            "component_overlap_mean": (
                mean(component_overlap_values) if component_overlap_values else 0.0
            ),
        },
        "certificate_consequences": {
            "admitted_union_edges": sum(
                certificate.decision.value == "ADMIT" for certificate in edge_certificates
            ),
            "qualified_union_edges": sum(
                certificate.decision.value == "QUALIFY"
                for certificate in edge_certificates
            ),
            "admitted_default_edges": sum(
                certificate.decision.value == "ADMIT"
                for certificate in default_edge_certificates
            ),
            "qualified_default_edges": sum(
                certificate.decision.value == "QUALIFY"
                for certificate in default_edge_certificates
            ),
            "survival_gate": 0.8,
            "gate_status": "author-specified heuristic, not a universal threshold",
        },
        "gate_frontier": _gate_frontier(edge_survival, "union"),
        "default_gate_frontier": _gate_frontier(
            default_edge_survival, "default"
        ),
        "configurations": results,
    }