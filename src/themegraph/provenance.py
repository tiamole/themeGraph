"""Deterministic digests for source files and consumed document sequences."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from themegraph.models import DocumentRecord


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def document_sequence_sha256(documents: Iterable[DocumentRecord]) -> str:
    digest = hashlib.sha256()
    for document in documents:
        payload = json.dumps(
            {
                "document_id": document.document_id,
                "text": document.text,
                "metadata": document.metadata,
                "provenance": document.provenance,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(payload).to_bytes(8, byteorder="big"))
        digest.update(payload)
    return digest.hexdigest()