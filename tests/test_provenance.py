from themegraph.models import DocumentRecord
from themegraph.provenance import document_sequence_sha256


def test_document_sequence_digest_is_stable_and_order_sensitive() -> None:
    left = DocumentRecord("1", "alpha", {"source": "a"}, "fixture")
    right = DocumentRecord("2", "beta", {"source": "b"}, "fixture")

    assert document_sequence_sha256([left, right]) == document_sequence_sha256(
        [left, right]
    )
    assert document_sequence_sha256([left, right]) != document_sequence_sha256(
        [right, left]
    )