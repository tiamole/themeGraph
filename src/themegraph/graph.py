"""Directed graph primitives and iterative strongly connected component analysis."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable
from dataclasses import dataclass, field

Node = Hashable


@dataclass(slots=True)
class DirectedGraph:
    """A complete adjacency mapping that preserves isolated nodes."""

    adjacency: dict[Node, set[Node]] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        self.adjacency.setdefault(node, set())

    def add_edge(self, source: Node, target: Node) -> None:
        self.add_node(source)
        self.add_node(target)
        self.adjacency[source].add(target)

    @classmethod
    def from_edges(
        cls,
        edges: Iterable[tuple[Node, Node]],
        nodes: Iterable[Node] = (),
    ) -> DirectedGraph:
        graph = cls()
        for node in nodes:
            graph.add_node(node)
        for source, target in edges:
            graph.add_edge(source, target)
        return graph

    @property
    def nodes(self) -> set[Node]:
        return set(self.adjacency)

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self.adjacency.values())

    def strongly_connected_components(self) -> list[frozenset[Node]]:
        """Return SCCs using iterative Tarjan traversal in O(V + E) time."""
        index = 0
        indices: dict[Node, int] = {}
        lowlink: dict[Node, int] = {}
        tarjan_stack: list[Node] = []
        on_stack: set[Node] = set()
        components: list[frozenset[Node]] = []

        for root in self.adjacency:
            if root in indices:
                continue

            indices[root] = index
            lowlink[root] = index
            index += 1
            tarjan_stack.append(root)
            on_stack.add(root)
            frames: list[tuple[Node, object, Node | None]] = [
                (root, iter(self.adjacency[root]), None)
            ]

            while frames:
                node, neighbors, parent = frames[-1]
                try:
                    neighbor = next(neighbors)  # type: ignore[arg-type]
                except StopIteration:
                    frames.pop()
                    if parent is not None:
                        lowlink[parent] = min(lowlink[parent], lowlink[node])
                    if lowlink[node] == indices[node]:
                        component: set[Node] = set()
                        while True:
                            member = tarjan_stack.pop()
                            on_stack.remove(member)
                            component.add(member)
                            if member == node:
                                break
                        components.append(frozenset(component))
                    continue

                if neighbor not in indices:
                    indices[neighbor] = index
                    lowlink[neighbor] = index
                    index += 1
                    tarjan_stack.append(neighbor)
                    on_stack.add(neighbor)
                    frames.append((neighbor, iter(self.adjacency[neighbor]), node))
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], indices[neighbor])

        return components

    def weakly_connected_components(self) -> list[frozenset[Node]]:
        undirected: dict[Node, set[Node]] = {node: set() for node in self.adjacency}
        for source, targets in self.adjacency.items():
            for target in targets:
                undirected[source].add(target)
                undirected[target].add(source)

        remaining = set(undirected)
        components: list[frozenset[Node]] = []
        while remaining:
            root = remaining.pop()
            component = {root}
            queue = deque([root])
            while queue:
                node = queue.popleft()
                unseen = undirected[node] & remaining
                remaining.difference_update(unseen)
                component.update(unseen)
                queue.extend(unseen)
            components.append(frozenset(component))
        return components

    def condensation(
        self, components: list[frozenset[Node]] | None = None
    ) -> tuple[DirectedGraph, dict[Node, int]]:
        components = components or self.strongly_connected_components()
        membership = {
            node: component_index
            for component_index, component in enumerate(components)
            for node in component
        }
        condensed = DirectedGraph()
        for component_index in range(len(components)):
            condensed.add_node(component_index)
        for source, targets in self.adjacency.items():
            source_component = membership[source]
            for target in targets:
                target_component = membership[target]
                if source_component != target_component:
                    condensed.add_edge(source_component, target_component)
        return condensed, membership

    def topological_order(self) -> list[Node]:
        in_degree: dict[Node, int] = {node: 0 for node in self.adjacency}
        for targets in self.adjacency.values():
            for target in targets:
                in_degree[target] += 1

        queue = deque(node for node, degree in in_degree.items() if degree == 0)
        order: list[Node] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for target in self.adjacency[node]:
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)
        if len(order) != len(self.adjacency):
            raise ValueError("Topological order is undefined for a cyclic graph")
        return order

    def bridge_nodes(self, membership: dict[Node, int]) -> dict[Node, int]:
        """Count distinct external components reached by each original node."""
        scores: dict[Node, set[int]] = defaultdict(set)
        for source, targets in self.adjacency.items():
            for target in targets:
                if membership[source] != membership[target]:
                    scores[source].add(membership[target])
        return {node: len(target_components) for node, target_components in scores.items()}
