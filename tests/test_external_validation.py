from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pyarrow as arrow
from pyarrow import parquet

from themegraph.admissibility import ClaimType
from themegraph.external_validation import lexical_jaccard, run_external_validation


def _write_pairs(path: Path, rows: list[tuple[str, str, int]]) -> None:
    table = arrow.table(
        {
            "sentence1": [row[0] for row in rows],
            "sentence2": [row[1] for row in rows],
            "label": [row[2] for row in rows],
        }
    )
    parquet.write_table(table, path)


def _write_snli(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for split in ("train", "dev", "test"):
            rows = [
                {
                    "sentence1": "A person runs",
                    "sentence2": "A person moves",
                    "gold_label": "entailment",
                },
                {
                    "sentence1": "A person runs",
                    "sentence2": "Nobody moves",
                    "gold_label": "contradiction",
                },
                {
                    "sentence1": "A person runs",
                    "sentence2": "It is morning",
                    "gold_label": "neutral",
                },
            ]
            payload = "".join(json.dumps(row) + "\n" for row in rows)
            archive.writestr(f"snli_1.0/snli_1.0_{split}.jsonl", payload)


def _write_al_cpl(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for domain in ("data_mining", "geometry", "physics", "precalculus"):
            archive.writestr(
                f"AL-CPL/data/{domain}.pairs",
                "Advanced,Foundation\nFoundation,Advanced\nAdvanced,Unrelated\n",
            )
            archive.writestr(
                f"AL-CPL/data/{domain}.preqs",
                "Advanced,Foundation\n",
            )


def _write_torque(path: Path) -> None:
    dev = {
        "passage-1": {
            "passage": "First happened. Second happened.",
            "question_answer_pairs": {
                "What happened before second?": {
                    "answer": {"indices": ["(0,5)"], "spans": ["First"]}
                },
                "What happened after first?": {
                    "answer": {"indices": ["(16,22)"], "spans": ["Second"]}
                },
            },
        }
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("TORQUE/data/dev.json", json.dumps(dev))
        archive.writestr("TORQUE/data/test.json", "{}")


def test_lexical_jaccard_uses_unique_casefolded_tokens() -> None:
    assert lexical_jaccard("A cat CAT", "a dog") == 1 / 3


def test_external_validation_is_construct_matched_and_aggregate_only(
    tmp_path: Path,
) -> None:
    external = tmp_path / "data" / "external"
    external.mkdir(parents=True)
    rows = [
        ("A B C D", "A B C D", 1),
        ("A B C D", "A B D C", 0),
    ]
    for dataset in ("mrpc", "paws"):
        for split in ("train", "validation", "test"):
            _write_pairs(external / f"{dataset}_{split}.parquet", rows)
    _write_snli(external / "snli_1.0.zip")
    _write_al_cpl(external / "al_cpl_11397eaa.zip")
    _write_torque(external / "torque_ab27019c.zip")

    result = run_external_validation(tmp_path)

    assert result["raw_text_redistributed"] is False
    assert result["datasets"]["mrpc"]["record_count"] == 6
    assert result["datasets"]["paws"]["lexical_overlap"][
        "high_overlap_non_paraphrase_rate"
    ] == 1.0
    for dataset in result["datasets"].values():
        assert dataset["contract_outcomes"]["cross_construct_admission_rate"] == 0.0
        assert "sentence1" not in json.dumps(dataset)
        assert all(
            route["policy_version"] == result["policy_version"]
            and len(route["route_id"]) == 16
            and route["request_count"] > 0
            and route["observed_consequence"]
            in {route["expected_consequence"], "NOT_EVALUATED"}
            for route in dataset["contract_routes"]
        )
        cross_routes = [
            route
            for route in dataset["contract_routes"]
            if route["evidence_condition"] == "cross-construct request"
        ]
        assert cross_routes
        assert all(route["requested_claim"] in ClaimType for route in cross_routes)
        assert all(route["request_count"] > 0 for route in cross_routes)
        assert all(route["observed_consequence"] == "REFUSE" for route in cross_routes)
        assert all(len(route["route_id"]) == 16 for route in cross_routes)
        assert "excluded-claim-types-aggregate" not in json.dumps(cross_routes)
    for dataset_id in ("mrpc", "paws"):
        routes = {
            route["evidence_condition"]: route
            for route in result["datasets"][dataset_id]["contract_routes"]
        }
        assert routes["matched positive annotation"]["requested_claim"] == (
            "sentential-paraphrase-equivalence"
        )
        assert routes["negative annotation"]["requested_claim"] == (
            "sentential-paraphrase-equivalence"
        )
        assert routes["matched non-paraphrase annotation"]["requested_claim"] == (
            "sentential-non-paraphrase"
        )
    assert result["datasets"]["snli"]["contract_outcomes"][
        "directional_annotation_admission_rate"
    ] == 1.0
    snli = result["datasets"]["snli"]
    assert snli["contract_outcomes"]["neutral_insufficient_support_refusal_rate"] == 1.0
    assert snli["contract_outcomes"]["contradiction_counterevidence_refusal_rate"] == 1.0
    assert snli["lexical_overlap"]["high_overlap_non_entailment_count"] == sum(
        snli["lexical_overlap"]["by_label"][label]["high_overlap_count"]
        for label in ("neutral", "contradiction")
    )
    assert snli["lexical_overlap"]["by_label"]["neutral"]["count"] == 3
    al_cpl = result["datasets"]["al_cpl"]
    assert al_cpl["record_count"] == 12
    assert al_cpl["label_counts"] == {
        "prerequisite": 4,
        "non_prerequisite": 8,
    }
    assert al_cpl["contract_outcomes"]["matched_annotation_admission_rate"] == 1.0
    assert al_cpl["contract_outcomes"]["reverse_nontransfer_refusal_rate"] == 1.0
    assert all(
        domain["asymmetry_violation_count"] == 0
        for domain in al_cpl["domain_summaries"].values()
    )
    torque = result["datasets"]["torque"]
    assert torque["split_counts"] == {"dev_passages": 1}
    assert torque["record_count"] == 2
    assert torque["contract_outcomes"]["mention_order_refusal_rate"] == 1.0
    assert torque["contract_outcomes"]["mention_order_triggered_reasons"] == [
        "mention-order-insufficient"
    ]
    assert torque["contract_outcomes"]["reverse_nontransfer_refusal_rate"] == 1.0
