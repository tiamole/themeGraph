"""Evaluation metrics for graph structure, partitions, and falsification baselines."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from math import comb
from typing import Any

import networkx as nx
import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans, SpectralClustering

from themegraph.graph import DirectedGraph
from themegraph.models import AnalysisResult


def partition_labels(components: list[frozenset[str]]) -> dict[str, int]:
    return {
        node: component_index
        for component_index, component in enumerate(components)
        for node in component
    }


def pairwise_partition_scores(
    predicted: dict[str, int], expected: dict[str, str]
) -> dict[str, float]:
    nodes = sorted(predicted.keys() & expected.keys())
    true_positive = false_positive = false_negative = 0
    for left, right in combinations(nodes, 2):
        predicted_same = predicted[left] == predicted[right]
        expected_same = expected[left] == expected[right]
        if predicted_same and expected_same:
            true_positive += 1
        elif predicted_same:
            false_positive += 1
        elif expected_same:
            false_negative += 1
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "evaluated_nodes": len(nodes)}


def adjusted_rand_index(predicted: dict[str, int], expected: dict[str, str]) -> float:
    nodes = sorted(predicted.keys() & expected.keys())
    if len(nodes) < 2:
        return 0.0
    contingency = Counter((predicted[node], expected[node]) for node in nodes)
    predicted_sizes = Counter(predicted[node] for node in nodes)
    expected_sizes = Counter(expected[node] for node in nodes)
    sum_cells = sum(comb(count, 2) for count in contingency.values())
    sum_predicted = sum(comb(count, 2) for count in predicted_sizes.values())
    sum_expected = sum(comb(count, 2) for count in expected_sizes.values())
    total_pairs = comb(len(nodes), 2)
    expected_index = sum_predicted * sum_expected / total_pairs
    maximum_index = (sum_predicted + sum_expected) / 2
    denominator = maximum_index - expected_index
    return (sum_cells - expected_index) / denominator if denominator else 1.0


def structural_metrics(result: AnalysisResult) -> dict[str, Any]:
    edge_pairs = {(edge.source, edge.target) for edge in result.edges}
    asymmetric_edges = sum((target, source) not in edge_pairs for source, target in edge_pairs)
    nontrivial_components = [component for component in result.components if len(component) > 1]
    largest = max((len(component) for component in result.components), default=0)
    return {
        "documents": result.document_count,
        "units": result.unit_count,
        "nodes": len(result.nodes),
        "edges": len(result.edges),
        "scc_count": len(result.components),
        "weak_component_count": len(result.weak_components),
        "nontrivial_scc_count": len(nontrivial_components),
        "largest_scc": largest,
        "singleton_rate": (
            sum(len(component) == 1 for component in result.components) / len(result.components)
            if result.components
            else 0.0
        ),
        "asymmetric_edge_rate": asymmetric_edges / len(edge_pairs) if edge_pairs else 0.0,
        "scc_partition_equals_weak_partition": {
            frozenset(component) for component in result.components
        }
        == {frozenset(component) for component in result.weak_components},
        "condensation_edge_count": len(result.condensation_edges),
        "bridge_node_count": len(result.bridge_scores),
    }


def symmetrized_baseline(result: AnalysisResult) -> dict[str, Any]:
    directed_edges = {(edge.source, edge.target) for edge in result.edges}
    reciprocal_edges = directed_edges | {(target, source) for source, target in directed_edges}
    graph = DirectedGraph.from_edges(reciprocal_edges, nodes=result.nodes)
    components = graph.strongly_connected_components()
    return {
        "component_count": len(components),
        "largest_component": max((len(component) for component in components), default=0),
        "partition": [sorted(str(node) for node in component) for component in components],
    }


def directional_ablations(result: AnalysisResult) -> dict[str, Any]:
    reversed_graph = DirectedGraph.from_edges(
        ((edge.target, edge.source) for edge in result.edges), nodes=result.nodes
    )
    reversed_components = reversed_graph.strongly_connected_components()
    return {
        "reverse_all_edges": {
            "component_count": len(reversed_components),
            "largest_component": max(
                (len(component) for component in reversed_components), default=0
            ),
            "partition_unchanged": {
                frozenset(component) for component in reversed_components
            }
            == {frozenset(component) for component in result.components},
        },
        "remove_all_relations_no_scc": {
            "component_count": len(result.nodes),
            "largest_component": 1 if result.nodes else 0,
            "partition": [[node] for node in sorted(result.nodes)],
        },
        "remove_bridge_scoring": {
            "core_partition_unchanged": True,
            "removed_bridge_nodes": len(result.bridge_scores),
        },
        "remove_condensation_ordering": {
            "core_partition_unchanged": True,
            "removed_condensation_edges": len(result.condensation_edges),
        },
    }


def community_baselines(result: AnalysisResult, seed: int = 2027) -> dict[str, Any]:
    graph = nx.Graph()
    graph.add_nodes_from(result.nodes)
    for edge in result.edges:
        if graph.has_edge(edge.source, edge.target):
            graph[edge.source][edge.target]["weight"] = max(
                graph[edge.source][edge.target]["weight"], edge.confidence
            )
        else:
            graph.add_edge(edge.source, edge.target, weight=edge.confidence)

    if graph.number_of_edges() == 0:
        singleton_partition = [[node] for node in sorted(graph.nodes)]
        return {"greedy_modularity": singleton_partition, "louvain": singleton_partition}

    greedy = nx.community.greedy_modularity_communities(graph, weight="weight")
    louvain = nx.community.louvain_communities(graph, weight="weight", seed=seed)
    return {
        "greedy_modularity": [sorted(str(node) for node in group) for group in greedy],
        "louvain": [sorted(str(node) for node in group) for group in louvain],
    }


def vector_clustering_baselines(
    result: AnalysisResult, n_clusters: int, seed: int = 2027
) -> dict[str, dict[str, int]]:
    """Cluster nodes using identical directed edge-profile features."""

    nodes = sorted(result.nodes)
    node_index = {node: index for index, node in enumerate(nodes)}
    profiles = np.zeros((len(nodes), len(nodes) * 2), dtype=float)
    affinity = np.eye(len(nodes), dtype=float)
    for edge in result.edges:
        source = node_index[edge.source]
        target = node_index[edge.target]
        profiles[source, target] = max(profiles[source, target], edge.confidence)
        profiles[target, len(nodes) + source] = max(
            profiles[target, len(nodes) + source], edge.confidence
        )
        affinity[source, target] = affinity[target, source] = max(
            affinity[source, target], edge.confidence
        )

    estimators = {
        "kmeans": KMeans(n_clusters=n_clusters, random_state=seed, n_init=20),
        "agglomerative": AgglomerativeClustering(n_clusters=n_clusters),
        "spectral": SpectralClustering(
            n_clusters=n_clusters,
            affinity="precomputed",
            assign_labels="kmeans",
            random_state=seed,
        ),
    }
    partitions: dict[str, dict[str, int]] = {}
    for name, estimator in estimators.items():
        features = affinity if name == "spectral" else profiles
        labels = estimator.fit_predict(features)
        partitions[name] = {
            node: int(label) for node, label in zip(nodes, labels, strict=True)
        }
    return partitions

