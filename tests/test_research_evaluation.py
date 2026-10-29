from scripts.run_research_evaluation import deduplicate_by_normalized_text, threshold_sweep
from themegraph.models import DocumentRecord


def test_deduplicate_by_normalized_text_preserves_first_document() -> None:
    documents = [
        DocumentRecord("first", "Build   systems", provenance="fixture"),
        DocumentRecord("duplicate", " Build systems ", provenance="fixture"),
        DocumentRecord("distinct", "Test systems", provenance="fixture"),
    ]

    result = deduplicate_by_normalized_text(documents)

    assert [document.document_id for document in result] == ["first", "distinct"]


def test_threshold_sweep_preserves_completed_rows_without_recomputation() -> None:
    completed = [
        {
            "min_confidence": confidence,
            "min_lift": lift,
            "largest_scc": 1,
        }
        for confidence in (0.5, 0.65, 0.8)
        for lift in (1.0, 1.05, 1.25)
    ]

    result = threshold_sweep("fixture", [], completed_rows=completed)

    assert result == completed