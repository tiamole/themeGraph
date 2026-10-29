"""Synthetic corpora with planted cycles and asymmetric bridge relations."""

from __future__ import annotations

import random

from themegraph.models import DocumentRecord


def planted_cycle_corpus(
    documents_per_group: int = 30, seed: int = 2027
) -> tuple[list[DocumentRecord], dict[str, str]]:
    random_generator = random.Random(seed)
    groups = {
        "control": ("automation", "control", "sensor"),
        "safety": ("hazard", "inspection", "safety"),
        "collaboration": ("communication", "coordination", "teamwork"),
    }
    specialties = {
        "control": "calibration",
        "safety": "compliance",
        "collaboration": "presentation",
    }
    labels = {term: label for label, terms in groups.items() for term in terms}
    documents: list[DocumentRecord] = []
    for label, terms in groups.items():
        for document_index in range(documents_per_group):
            shuffled = list(terms)
            random_generator.shuffle(shuffled)
            words = [*shuffled, "system"]
            if document_index % 3 == 0:
                words.append(specialties[label])
            documents.append(
                DocumentRecord(
                    document_id=f"synthetic-{label}-{document_index}",
                    text=" ".join(words) + ".",
                    metadata={"planted_group": label},
                    provenance=f"generated:seed={seed}",
                )
            )
    return documents, labels
