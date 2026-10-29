from themegraph.models import DocumentRecord
from themegraph.specification import (
    _component_overlap,
    evaluate_specification_surface,
    interaction_grid,
    specification_grid,
)


def test_component_overlap_uses_one_to_one_matching() -> None:
    overlap = _component_overlap(
        {("a", "b"), ("c", "d")},
        [{("a", "b", "c", "d")}],
    )

    assert sorted(overlap.values()) == [0.0, 0.5]


def test_specification_grid_varies_declared_axes_without_duplicates() -> None:
    grid = specification_grid(include_bigrams=False)

    assert len(grid) == len({item.identifier for item in grid})
    assert {item.unit_mode for item in grid} == {
        "sentence",
        "paragraph",
        "sentence-window",
    }
    assert {item.max_vocabulary for item in grid} == {100, 250, 500, 1000}
    assert {item.exact_deduplication for item in grid} == {False, True}
    interactions = interaction_grid(include_bigrams=False)
    assert len(interactions) == 6
    assert not ({item.identifier for item in grid} & {item.identifier for item in interactions})


def test_specification_surface_reports_survival_and_certificate_consequences() -> None:
    documents = [
        DocumentRecord(
            f"alpha-{index}",
            "Alpha beta. Alpha beta.",
            provenance="fixture",
        )
        for index in range(6)
    ]
    documents.extend(
        DocumentRecord(
            f"gamma-{index}",
            "Gamma delta. Gamma delta.",
            provenance="fixture",
        )
        for index in range(6)
    )

    result = evaluate_specification_surface(
        documents, "fixture", include_bigrams=False
    )

    assert result["configuration_count"] == len(specification_grid(False)) + len(
        interaction_grid(False)
    )
    assert result["one_factor_configuration_count"] == len(specification_grid(False))
    assert result["bounded_interaction_configuration_count"] == 6
    assert result["baseline_edge_count"] > 0
    assert result["edge_survival"]
    assert len(result["edge_survival"]) == result["union_edge_count"]
    assert len(result["default_edge_survival"]) == result["baseline_edge_count"]
    assert "exhaustive Cartesian interactions" in result["unevaluated_axes"]
    geometry = result["edge_set_geometry"]
    assert geometry["intersection_count"] <= geometry["baseline_count"]
    assert geometry["union_count"] >= geometry["baseline_count"]
    assert 0.0 <= geometry["baseline_jaccard"]["minimum"] <= 1.0
    assert len(result["gate_frontier"]) == 6
    assert result["component_one_to_one_jaccard"]
    assert result["component_matching"].startswith("maximum-weight one-to-one")
    consequences = result["certificate_consequences"]
    assert consequences["admitted_default_edges"] + consequences[
        "qualified_default_edges"
    ] == result["baseline_edge_count"]
    assert consequences["admitted_union_edges"] + consequences[
        "qualified_union_edges"
    ] == result["union_edge_count"]