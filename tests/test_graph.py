import random

import networkx as nx

from themegraph.graph import DirectedGraph


def normalize(components):
    return {frozenset(component) for component in components}


def test_canonical_sccs_include_isolated_and_destination_only_nodes():
    graph = DirectedGraph.from_edges(
        [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "e")],
        nodes=["isolated"],
    )

    assert normalize(graph.strongly_connected_components()) == {
        frozenset({"a", "b", "c"}),
        frozenset({"d"}),
        frozenset({"e"}),
        frozenset({"isolated"}),
    }


def test_every_component_in_a_dag_is_a_singleton():
    graph = DirectedGraph.from_edges([(0, 1), (0, 2), (2, 3)], nodes=range(5))

    assert all(len(component) == 1 for component in graph.strongly_connected_components())
    assert len(graph.strongly_connected_components()) == 5


def test_reciprocal_edges_make_sccs_equal_weak_components():
    reciprocal_edges = [("a", "b"), ("b", "a"), ("b", "c"), ("c", "b")]
    graph = DirectedGraph.from_edges(reciprocal_edges, nodes=["isolated"])

    assert normalize(graph.strongly_connected_components()) == normalize(
        graph.weakly_connected_components()
    )


def test_condensation_is_acyclic_and_preserves_all_components():
    graph = DirectedGraph.from_edges(
        [("a", "b"), ("b", "a"), ("b", "c"), ("c", "d"), ("d", "c")]
    )
    components = graph.strongly_connected_components()
    condensed, membership = graph.condensation(components)

    assert len(condensed.nodes) == 2
    assert condensed.edge_count == 1
    assert len(condensed.topological_order()) == 2
    assert membership["a"] == membership["b"]
    assert membership["c"] == membership["d"]
    assert membership["a"] != membership["c"]


def test_iterative_tarjan_handles_long_paths_without_recursion():
    graph = DirectedGraph.from_edges((node, node + 1) for node in range(5000))

    assert len(graph.strongly_connected_components()) == 5001


def test_iterative_tarjan_matches_networkx_on_generated_graphs():
    generator = random.Random(2027)
    for node_count in range(1, 31):
        nodes = list(range(node_count))
        edges = [
            (source, target)
            for source in nodes
            for target in nodes
            if generator.random() < 0.12
        ]
        graph = DirectedGraph.from_edges(edges, nodes=nodes)
        reference = nx.DiGraph()
        reference.add_nodes_from(nodes)
        reference.add_edges_from(edges)

        assert normalize(graph.strongly_connected_components()) == normalize(
            nx.strongly_connected_components(reference)
        )