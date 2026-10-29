"""Construct-matched policy stress tests over external annotated datasets."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pyarrow import parquet

from themegraph.admissibility import (
    POLICY_VERSION,
    ClaimType,
    Decision,
    EvidenceBundle,
    EvidenceChannel,
    EvidencePolarity,
    EvidenceRecord,
    GovernedObject,
    ObjectType,
    evaluate_claim,
)
from themegraph.provenance import sha256_file

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
HIGH_OVERLAP_THRESHOLD = 0.5
OVERLAP_BIN_EDGES = tuple(index / 10 for index in range(11))

MRPC_MIRROR_URLS = {
    split: (
        "https://huggingface.co/datasets/nyu-mll/glue/resolve/"
        f"refs%2Fconvert%2Fparquet/mrpc/{split}/0000.parquet"
    )
    for split in ("train", "validation", "test")
}
PAWS_MIRROR_URLS = {
    split: (
        "https://huggingface.co/datasets/google-research-datasets/paws/resolve/"
        f"refs%2Fconvert%2Fparquet/labeled_final/{split}/0000.parquet"
    )
    for split in ("train", "validation", "test")
}
SNLI_SOURCE_URL = "https://nlp.stanford.edu/projects/snli/snli_1.0.zip"
AL_CPL_COMMIT = "11397eaa3ea01c5e06fefcfc1c02a84f21164081"
AL_CPL_SOURCE_URL = (
    "https://github.com/harrylclc/AL-CPL-dataset/archive/"
    f"{AL_CPL_COMMIT}.zip"
)
TORQUE_COMMIT = "ab27019cc6a317fde3c879900499f02acce8b16d"
TORQUE_SOURCE_URL = (
    "https://github.com/qiangning/TORQUE-dataset/archive/"
    f"{TORQUE_COMMIT}.zip"
)
AL_CPL_DOMAINS = ("data_mining", "geometry", "physics", "precalculus")
TEMPORAL_QUESTION_PATTERN = re.compile(r"\b(before|after)\b", re.IGNORECASE)


def lexical_jaccard(first: str, second: str) -> float:
    first_tokens = set(TOKEN_PATTERN.findall(first.casefold()))
    second_tokens = set(TOKEN_PATTERN.findall(second.casefold()))
    union = first_tokens | second_tokens
    return len(first_tokens & second_tokens) / len(union) if union else 1.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def _overlap_summary(values: list[float]) -> dict[str, Any]:
    histogram = [0] * (len(OVERLAP_BIN_EDGES) - 1)
    for value in values:
        histogram[min(int(value * 10), 9)] += 1
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else 0.0,
        "p25": _percentile(values, 0.25),
        "median": _percentile(values, 0.5),
        "p75": _percentile(values, 0.75),
        "high_overlap_count": sum(
            value >= HIGH_OVERLAP_THRESHOLD for value in values
        ),
        "histogram_bin_edges": OVERLAP_BIN_EDGES,
        "histogram_counts": histogram,
    }


def _parquet_pairs(paths: dict[str, Path]) -> Iterator[tuple[str, str, str, int]]:
    for split, path in paths.items():
        source = parquet.ParquetFile(path)
        for batch in source.iter_batches(columns=["sentence1", "sentence2", "label"]):
            data = batch.to_pydict()
            for first, second, label in zip(
                data["sentence1"], data["sentence2"], data["label"], strict=True
            ):
                yield split, str(first), str(second), int(label)


def _snli_pairs(path: Path) -> Iterator[tuple[str, str, str, str]]:
    with zipfile.ZipFile(path) as archive:
        for split in ("train", "dev", "test"):
            member = f"snli_1.0/snli_1.0_{split}.jsonl"
            with archive.open(member) as stream:
                for line in stream:
                    row = json.loads(line)
                    label = str(row["gold_label"])
                    if label == "-":
                        continue
                    yield split, str(row["sentence1"]), str(row["sentence2"]), label


def _source_records(paths: dict[str, Path], urls: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "split": split,
            "path": f"data/external/{path.name}",
            "source_url": urls[split],
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for split, path in paths.items()
    ]


def _semantic_contract_outcomes(label_counts: Counter[int]) -> dict[str, Any]:
    relation = ("sentence-a", "sentence-b")
    governed_object = GovernedObject(
        relation[0], ObjectType.SENTENCE, relation[1], ObjectType.SENTENCE
    )
    lexical = EvidenceBundle(
        frozenset({EvidenceChannel.CO_OCCURRENCE}),
        governed_object=governed_object,
    )
    positive = EvidenceBundle(
        channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
                polarity=EvidencePolarity.SUPPORT,
                relation=relation,
                source="documented human paraphrase annotation",
            ),
        ),
        governed_object=governed_object,
    )
    negative_counterevidence = EvidenceBundle(
        channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                target=ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE,
                polarity=EvidencePolarity.COUNTEREVIDENCE,
                relation=relation,
                source="documented human non-paraphrase annotation",
            ),
        ),
        governed_object=governed_object,
    )
    negative_support = EvidenceBundle(
        channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.ANNOTATION_SEMANTIC_EQUIVALENCE,
                target=ClaimType.SENTENTIAL_NON_PARAPHRASE,
                polarity=EvidencePolarity.SUPPORT,
                relation=relation,
                source="documented human non-paraphrase annotation",
            ),
        ),
        governed_object=governed_object,
    )
    mismatch_claims = (
        ClaimType.TEXTUAL_ENTAILMENT,
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        ClaimType.CONCEPT_PREREQUISITE,
        ClaimType.CAUSAL_INFLUENCE,
        ClaimType.THEME,
        ClaimType.ANALYST_BENEFIT,
    )
    mismatch_certificates = [
        evaluate_claim(claim_type, positive) for claim_type in mismatch_claims
    ]
    return {
        "lexical_only_positive_claim_refusal_rate": float(
            evaluate_claim(ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, lexical).decision
            is Decision.REFUSE
        ),
        "positive_annotation_admission_rate": (
            float(
                evaluate_claim(ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, positive).decision
                is Decision.ADMIT
            )
            if label_counts[1]
            else None
        ),
        "negative_counterevidence_refusal_rate": (
            float(
                evaluate_claim(
                    ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, negative_counterevidence
                ).decision
                is Decision.REFUSE
            )
            if label_counts[0]
            else None
        ),
        "negative_claim_admission_rate": (
            float(
                evaluate_claim(
                    ClaimType.SENTENTIAL_NON_PARAPHRASE, negative_support
                ).decision
                is Decision.ADMIT
            )
            if label_counts[0]
            else None
        ),
        "cross_construct_admission_rate": sum(
            certificate.decision is Decision.ADMIT
            for certificate in mismatch_certificates
        ) / len(mismatch_certificates),
        "cross_construct_requests": [
            {
                "requested_claim": certificate.claim_type.value,
                "request_count": 1,
                "expected_consequence": Decision.REFUSE.value,
                "observed_consequence": certificate.decision.value,
            }
            for certificate in mismatch_certificates
        ],
    }


def _summarize_paraphrase_dataset(
    dataset_id: str,
    tier: str,
    paths: dict[str, Path],
    urls: dict[str, str],
    license_status: str,
) -> dict[str, Any]:
    labels: Counter[int] = Counter()
    splits: Counter[str] = Counter()
    overlap_by_label: dict[int, list[float]] = {0: [], 1: []}
    for split, first, second, label in _parquet_pairs(paths):
        labels[label] += 1
        splits[split] += 1
        overlap = lexical_jaccard(first, second)
        overlap_by_label[label].append(overlap)
    record_count = sum(labels.values())
    negative_overlap = _overlap_summary(overlap_by_label[0])
    positive_overlap = _overlap_summary(overlap_by_label[1])
    return {
        "dataset_id": dataset_id,
        "tier": tier,
        "validated_construct": "sentential paraphrase equivalence and non-paraphrase",
        "record_count": record_count,
        "split_counts": dict(sorted(splits.items())),
        "label_counts": {
            "non_paraphrase": labels[0],
            "paraphrase": labels[1],
        },
        "lexical_overlap": {
            "mean_jaccard": (
                sum(map(sum, overlap_by_label.values())) / record_count
                if record_count
                else 0.0
            ),
            "high_overlap_threshold": HIGH_OVERLAP_THRESHOLD,
            "high_overlap_non_paraphrase_count": negative_overlap[
                "high_overlap_count"
            ],
            "high_overlap_non_paraphrase_rate": (
                negative_overlap["high_overlap_count"] / negative_overlap["count"]
                if negative_overlap["count"]
                else 0.0
            ),
            "by_label": {
                "non_paraphrase": negative_overlap,
                "paraphrase": positive_overlap,
            },
        },
        "contract_outcomes": _semantic_contract_outcomes(labels),
        "license_status": license_status,
        "sources": _source_records(paths, urls),
        "excluded_claims": [
            "semantic entailment",
            "temporal precedence",
            "prerequisite",
            "causal influence",
            "theme",
            "analyst benefit",
        ],
    }


def _entailment_contract_outcomes(label_counts: Counter[str]) -> dict[str, Any]:
    relation = ("premise", "hypothesis")
    governed_object = GovernedObject(
        relation[0], ObjectType.SENTENCE, relation[1], ObjectType.SENTENCE
    )
    lexical = EvidenceBundle(
        frozenset({EvidenceChannel.CO_OCCURRENCE}),
        governed_object=governed_object,
    )
    directional = EvidenceBundle(
        channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.ANNOTATION_ENTAILMENT,
                target=ClaimType.TEXTUAL_ENTAILMENT,
                polarity=EvidencePolarity.SUPPORT,
                relation=relation,
                source="documented SNLI entailment annotation",
            ),
        ),
        governed_object=governed_object,
    )
    reversed_direction = EvidenceBundle(
        records=directional.records,
        governed_object=GovernedObject(
            relation[1], ObjectType.SENTENCE, relation[0], ObjectType.SENTENCE
        ),
    )
    neutral = EvidenceBundle(
        frozenset({EvidenceChannel.CO_OCCURRENCE}),
        governed_object=governed_object,
    )
    contradiction = EvidenceBundle(
        channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
        records=(
            EvidenceRecord(
                channel=EvidenceChannel.ANNOTATION_ENTAILMENT,
                target=ClaimType.TEXTUAL_ENTAILMENT,
                polarity=EvidencePolarity.COUNTEREVIDENCE,
                relation=relation,
                source="documented SNLI contradiction annotation",
            ),
        ),
        governed_object=governed_object,
    )
    mismatch_claims = (
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        ClaimType.CONCEPT_PREREQUISITE,
        ClaimType.CAUSAL_INFLUENCE,
        ClaimType.THEME,
        ClaimType.ANALYST_BENEFIT,
    )
    mismatch_certificates = [
        evaluate_claim(claim_type, directional) for claim_type in mismatch_claims
    ]
    return {
        "lexical_only_entailment_refusal_rate": float(
            evaluate_claim(ClaimType.TEXTUAL_ENTAILMENT, lexical).decision
            is Decision.REFUSE
        ),
        "directional_annotation_admission_rate": (
            float(
                evaluate_claim(ClaimType.TEXTUAL_ENTAILMENT, directional).decision
                is Decision.ADMIT
            )
            if label_counts["entailment"]
            else None
        ),
        "neutral_insufficient_support_refusal_rate": (
            float(
                evaluate_claim(ClaimType.TEXTUAL_ENTAILMENT, neutral).decision
                is Decision.REFUSE
            )
            if label_counts["neutral"]
            else None
        ),
        "contradiction_counterevidence_refusal_rate": (
            float(
                evaluate_claim(
                    ClaimType.TEXTUAL_ENTAILMENT, contradiction
                ).decision
                is Decision.REFUSE
            )
            if label_counts["contradiction"]
            else None
        ),
        "annotation_nontransfer_refusal_rate": float(
            evaluate_claim(
                ClaimType.TEXTUAL_ENTAILMENT, reversed_direction
            ).decision
            is Decision.REFUSE
        ),
        "cross_construct_admission_rate": sum(
            certificate.decision is Decision.ADMIT
            for certificate in mismatch_certificates
        ) / len(mismatch_certificates),
        "cross_construct_requests": [
            {
                "requested_claim": certificate.claim_type.value,
                "request_count": 1,
                "expected_consequence": Decision.REFUSE.value,
                "observed_consequence": certificate.decision.value,
            }
            for certificate in mismatch_certificates
        ],
    }


def _summarize_snli(path: Path) -> dict[str, Any]:
    labels: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    overlap_by_label: dict[str, list[float]] = {
        "entailment": [],
        "neutral": [],
        "contradiction": [],
    }
    for split, premise, hypothesis, label in _snli_pairs(path):
        labels[label] += 1
        splits[split] += 1
        overlap_by_label[label].append(lexical_jaccard(premise, hypothesis))
    record_count = sum(labels.values())
    overlap_summaries = {
        label: _overlap_summary(values)
        for label, values in overlap_by_label.items()
    }
    non_entailment_high_overlap = sum(
        overlap_summaries[label]["high_overlap_count"]
        for label in ("neutral", "contradiction")
    )
    return {
        "dataset_id": "snli-1.0",
        "tier": "directional human-annotated inference",
        "validated_construct": "premise-to-hypothesis semantic entailment",
        "record_count": record_count,
        "split_counts": dict(sorted(splits.items())),
        "label_counts": dict(sorted(labels.items())),
        "lexical_overlap": {
            "mean_jaccard": (
                sum(map(sum, overlap_by_label.values())) / record_count
                if record_count
                else 0.0
            ),
            "high_overlap_threshold": HIGH_OVERLAP_THRESHOLD,
            "high_overlap_non_entailment_count": non_entailment_high_overlap,
            "high_overlap_non_entailment_rate": (
                non_entailment_high_overlap
                / (labels["neutral"] + labels["contradiction"])
            ),
            "by_label": overlap_summaries,
        },
        "contract_outcomes": _entailment_contract_outcomes(labels),
        "license_status": "CC BY-SA 4.0 (Stanford NLP Group source page)",
        "sources": [
            {
                "path": f"data/external/{path.name}",
                "source_url": SNLI_SOURCE_URL,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        ],
        "excluded_claims": [
            "temporal precedence",
            "prerequisite",
            "causal influence",
            "theme",
            "analyst benefit",
        ],
    }


def _zip_member(archive: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"Expected one ZIP member ending in {suffix!r}, found {matches}")
    return matches[0]


def _al_cpl_pairs(
    archive: zipfile.ZipFile, domain: str, extension: str
) -> set[tuple[str, str]]:
    member = _zip_member(archive, f"/data/{domain}.{extension}")
    with archive.open(member) as stream:
        reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8"))
        rows = {
            (second.strip(), first.strip())
            for first, second in reader
            if first.strip() and second.strip()
        }
    return rows


def _directed_contract_outcomes(
    relations: list[tuple[str, str]],
    claim_type: ClaimType,
    channel: EvidenceChannel,
    source: str,
    mismatch_claim: ClaimType,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    mention_order_reasons: set[str] = set()
    object_type = {
        ClaimType.CONCEPT_PREREQUISITE: ObjectType.CONCEPT,
        ClaimType.EVENT_TEMPORAL_PRECEDENCE: ObjectType.EVENT,
    }[claim_type]
    for relation in relations:
        governed_object = GovernedObject(
            relation[0], object_type, relation[1], object_type
        )
        lexical = EvidenceBundle(
            channels=frozenset({EvidenceChannel.CO_OCCURRENCE}),
            governed_object=governed_object,
        )
        mention_order = EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.MENTION_ORDER,
                    target=claim_type,
                    relation=relation,
                    source="textual mention order only",
                ),
            ),
            governed_object=governed_object,
        )
        annotation = EvidenceRecord(
            channel=channel,
            target=claim_type,
            relation=relation,
            source=source,
        )
        matched = EvidenceBundle(
            records=(annotation,), governed_object=governed_object
        )
        reversed_request = EvidenceBundle(
            records=(annotation,),
            governed_object=GovernedObject(
                relation[1], object_type, relation[0], object_type
            ),
        )
        counts["lexical_refusal"] += (
            evaluate_claim(claim_type, lexical).decision is Decision.REFUSE
        )
        mention_order_certificate = evaluate_claim(claim_type, mention_order)
        counts["mention_order_refusal"] += (
            mention_order_certificate.decision is Decision.REFUSE
        )
        mention_order_reasons.update(
            reason.value for reason in mention_order_certificate.triggered_reasons
        )
        counts["matched_admission"] += (
            evaluate_claim(claim_type, matched).decision is Decision.ADMIT
        )
        counts["reverse_refusal"] += (
            evaluate_claim(claim_type, reversed_request).decision is Decision.REFUSE
        )
        counts["mismatch_admission"] += (
            evaluate_claim(mismatch_claim, matched).decision is Decision.ADMIT
        )
    denominator = len(relations)
    if not denominator:
        raise ValueError(f"No directed relations found for {claim_type.value}")
    return {
        "lexical_only_refusal_rate": counts["lexical_refusal"] / denominator,
        "mention_order_refusal_rate": counts["mention_order_refusal"] / denominator,
        "mention_order_triggered_reasons": sorted(mention_order_reasons),
        "matched_annotation_admission_rate": counts["matched_admission"] / denominator,
        "reverse_nontransfer_refusal_rate": counts["reverse_refusal"] / denominator,
        "cross_construct_admission_rate": counts["mismatch_admission"] / denominator,
        "cross_construct_requests": [
            {
                "requested_claim": mismatch_claim.value,
                "request_count": denominator,
                "expected_consequence": Decision.REFUSE.value,
                "observed_consequence": (
                    Decision.REFUSE.value
                    if counts["mismatch_admission"] == 0
                    else "DEVIATION"
                ),
            }
        ],
    }


def _summarize_al_cpl(path: Path) -> dict[str, Any]:
    domain_summaries: dict[str, dict[str, Any]] = {}
    all_positive: list[tuple[str, str]] = []
    all_negative: list[tuple[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        for domain in AL_CPL_DOMAINS:
            candidates = _al_cpl_pairs(archive, domain, "pairs")
            positives = _al_cpl_pairs(archive, domain, "preqs")
            if not positives <= candidates:
                raise ValueError(f"AL-CPL positives are not a subset of {domain} pairs")
            negatives = candidates - positives
            concepts = {concept for pair in candidates for concept in pair}
            reverse_negative_count = sum(
                tuple(reversed(relation)) in negatives for relation in positives
            )
            adjacency: dict[str, set[str]] = {}
            for source, target in positives:
                adjacency.setdefault(source, set()).add(target)
            compositions = {
                (source, target)
                for source, intermediate in positives
                for target in adjacency.get(intermediate, set())
                if source != target
            }
            domain_summaries[domain] = {
                "concept_count": len(concepts),
                "candidate_pair_count": len(candidates),
                "positive_pair_count": len(positives),
                "negative_pair_count": len(negatives),
                "irreflexive_violation_count": sum(
                    source == target for source, target in positives
                ),
                "asymmetry_violation_count": sum(
                    tuple(reversed(relation)) in positives for relation in positives
                ),
                "reverse_negative_count": reverse_negative_count,
                "reverse_negative_coverage_rate": reverse_negative_count / len(positives),
                "transitive_composition_count": len(compositions),
                "closed_transitive_composition_count": len(compositions & positives),
            }
            all_positive.extend(sorted(positives))
            all_negative.extend(sorted(negatives))
    outcomes = _directed_contract_outcomes(
        all_positive,
        ClaimType.CONCEPT_PREREQUISITE,
        EvidenceChannel.ANNOTATION_PREREQUISITE,
        "AL-CPL prerequisite annotation",
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
    )
    negative_refusals = 0
    for relation in all_negative:
        negative_counterevidence = EvidenceBundle(
            records=(
                EvidenceRecord(
                    channel=EvidenceChannel.ANNOTATION_PREREQUISITE,
                    target=ClaimType.CONCEPT_PREREQUISITE,
                    polarity=EvidencePolarity.COUNTEREVIDENCE,
                    relation=relation,
                    source="AL-CPL non-prerequisite annotation",
                ),
            ),
            governed_object=GovernedObject(
                relation[0],
                ObjectType.CONCEPT,
                relation[1],
                ObjectType.CONCEPT,
            ),
        )
        negative_refusals += (
            evaluate_claim(
                ClaimType.CONCEPT_PREREQUISITE, negative_counterevidence
            ).decision
            is Decision.REFUSE
        )
    outcomes["negative_counterevidence_refusal_rate"] = (
        negative_refusals / len(all_negative)
    )
    reverse_negative_count = sum(
        summary["reverse_negative_count"] for summary in domain_summaries.values()
    )
    transitive_composition_count = sum(
        summary["transitive_composition_count"]
        for summary in domain_summaries.values()
    )
    closed_transitive_composition_count = sum(
        summary["closed_transitive_composition_count"]
        for summary in domain_summaries.values()
    )
    return {
        "dataset_id": "al-cpl",
        "tier": "expert-corrected concept prerequisite annotations",
        "validated_construct": "directed concept prerequisite relation",
        "record_count": len(all_positive) + len(all_negative),
        "label_counts": {
            "prerequisite": len(all_positive),
            "non_prerequisite": len(all_negative),
        },
        "label_provenance": {
            "final_processed_positive_count": len(all_positive),
            "final_processed_negative_count": len(all_negative),
            "dataset_negative_corresponding_to_positive_reverse_count": reverse_negative_count,
            "observed_two_edge_composition_count": transitive_composition_count,
            "positive_closure_of_observed_composition_count": closed_transitive_composition_count,
            "record_level_original_or_derived_identifiable": False,
            "interpretation": (
                "The pinned release provides final processed relation data in .pairs "
                "and .preqs files within its data directory. Its README documents expert "
                "label correction, reverse-negative generation, and transitive-positive "
                "augmentation, but the released relations lack record-level derivation "
                "provenance. Counts therefore describe dataset-provided negatives that "
                "correspond to positive reversals and positive closures of observed "
                "two-edge compositions; they do not identify which rows were generated "
                "by preprocessing or independently confirm those preprocessing rules."
            ),
        },
        "domain_summaries": domain_summaries,
        "contract_outcomes": outcomes,
        "license_status": "CC BY-NC-SA 4.0; publication artifacts contain aggregates only.",
        "sources": [
            {
                "path": f"data/external/{path.name}",
                "source_url": AL_CPL_SOURCE_URL,
                "commit": AL_CPL_COMMIT,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        ],
        "excluded_claims": [
            "temporal precedence",
            "causal influence",
            "semantic entailment",
            "theme",
            "analyst benefit",
        ],
    }


def _summarize_torque(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        member = _zip_member(archive, "/data/dev.json")
        passages = json.loads(archive.read(member))
    question_count = 0
    directional_questions: Counter[str] = Counter()
    answerless_directional_questions = 0
    relations: list[tuple[str, str]] = []
    for passage_id, passage in passages.items():
        for question, annotation in passage["question_answer_pairs"].items():
            question_count += 1
            match = TEMPORAL_QUESTION_PATTERN.search(question)
            if match is None:
                continue
            direction = match.group(1).casefold()
            directional_questions[direction] += 1
            indices = annotation.get("answer", {}).get("indices", [])
            if not indices:
                answerless_directional_questions += 1
                continue
            focus_digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
            focus = f"{passage_id}:focus:{focus_digest}"
            for index in indices:
                answer = f"{passage_id}:event:{index}"
                relations.append(
                    (answer, focus) if direction == "before" else (focus, answer)
                )
    outcomes = _directed_contract_outcomes(
        relations,
        ClaimType.EVENT_TEMPORAL_PRECEDENCE,
        EvidenceChannel.ANNOTATION_TEMPORAL_PRECEDENCE,
        "TORQUE adjudicated dev annotation",
        ClaimType.CONCEPT_PREREQUISITE,
    )
    return {
        "dataset_id": "torque",
        "tier": "human-validated event temporal annotations",
        "validated_construct": "event temporal precedence",
        "record_count": len(relations),
        "split_counts": {"dev_passages": len(passages)},
        "label_counts": {
            "before_questions": directional_questions["before"],
            "after_questions": directional_questions["after"],
            "usable_relation_annotations": len(relations),
            "answerless_directional_questions": answerless_directional_questions,
        },
        "question_count": question_count,
        "contract_outcomes": outcomes,
        "license_status": "Apache 2.0 repository; public test answers are withheld and excluded.",
        "sources": [
            {
                "path": f"data/external/{path.name}",
                "source_url": TORQUE_SOURCE_URL,
                "commit": TORQUE_COMMIT,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "evaluated_split": "dev",
            }
        ],
        "excluded_claims": [
            "prerequisite",
            "causal influence",
            "semantic entailment",
            "theme",
            "analyst benefit",
        ],
    }


def _contract_routes(
    dataset_id: str, outcomes: dict[str, Any]
) -> list[dict[str, Any]]:
    route_specs = {
        "mrpc": (
            ("matched positive annotation", "positive_annotation_admission_rate", ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, "ADMIT", "authorized"),
            ("lexical evidence only", "lexical_only_positive_claim_refusal_rate", ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, "REFUSE", "missing construct-matched evidence"),
            ("negative annotation", "negative_counterevidence_refusal_rate", ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, "REFUSE", "construct-matched counterevidence"),
            ("matched non-paraphrase annotation", "negative_claim_admission_rate", ClaimType.SENTENTIAL_NON_PARAPHRASE, "ADMIT", "authorized"),
        ),
        "paws": (
            ("matched positive annotation", "positive_annotation_admission_rate", ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, "ADMIT", "authorized"),
            ("lexical evidence only", "lexical_only_positive_claim_refusal_rate", ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, "REFUSE", "missing construct-matched evidence"),
            ("negative annotation", "negative_counterevidence_refusal_rate", ClaimType.SENTENTIAL_PARAPHRASE_EQUIVALENCE, "REFUSE", "construct-matched counterevidence"),
            ("matched non-paraphrase annotation", "negative_claim_admission_rate", ClaimType.SENTENTIAL_NON_PARAPHRASE, "ADMIT", "authorized"),
        ),
        "snli": (
            ("matched directional annotation", "directional_annotation_admission_rate", ClaimType.TEXTUAL_ENTAILMENT, "ADMIT", "authorized"),
            ("neutral annotation", "neutral_insufficient_support_refusal_rate", ClaimType.TEXTUAL_ENTAILMENT, "REFUSE", "insufficient support"),
            ("contradiction annotation", "contradiction_counterevidence_refusal_rate", ClaimType.TEXTUAL_ENTAILMENT, "REFUSE", "construct-matched counterevidence"),
            ("reversed relation request", "annotation_nontransfer_refusal_rate", ClaimType.TEXTUAL_ENTAILMENT, "REFUSE", "scope mismatch"),
        ),
        "al_cpl": (
            ("matched prerequisite annotation", "matched_annotation_admission_rate", ClaimType.CONCEPT_PREREQUISITE, "ADMIT", "authorized"),
            ("lexical evidence only", "lexical_only_refusal_rate", ClaimType.CONCEPT_PREREQUISITE, "REFUSE", "missing construct-matched evidence"),
            ("mention order only", "mention_order_refusal_rate", ClaimType.CONCEPT_PREREQUISITE, "REFUSE", "evidence-channel-absent"),
            ("negative annotation", "negative_counterevidence_refusal_rate", ClaimType.CONCEPT_PREREQUISITE, "REFUSE", "construct-matched counterevidence"),
            ("reversed relation request", "reverse_nontransfer_refusal_rate", ClaimType.CONCEPT_PREREQUISITE, "REFUSE", "scope mismatch"),
        ),
        "torque": (
            ("matched event-order annotation", "matched_annotation_admission_rate", ClaimType.EVENT_TEMPORAL_PRECEDENCE, "ADMIT", "authorized"),
            ("mention order only", "mention_order_refusal_rate", ClaimType.EVENT_TEMPORAL_PRECEDENCE, "REFUSE", "mention-order-insufficient"),
            ("reversed relation request", "reverse_nontransfer_refusal_rate", ClaimType.EVENT_TEMPORAL_PRECEDENCE, "REFUSE", "scope mismatch"),
        ),
    }
    routes = []
    for condition, outcome_key, requested_claim, expected, path in route_specs[dataset_id]:
        claim_value = (
            requested_claim.value
            if isinstance(requested_claim, ClaimType)
            else requested_claim
        )
        conformance_rate = outcomes[outcome_key]
        if conformance_rate is None:
            observed = "NOT_EVALUATED"
        elif conformance_rate == 1.0:
            observed = expected
        else:
            observed = (
                Decision.REFUSE.value
                if expected == Decision.ADMIT.value
                else Decision.ADMIT.value
            )
        routes.append(
            {
                "route_id": hashlib.sha256(
                    f"{dataset_id}|{condition}|{claim_value}".encode()
                ).hexdigest()[:16],
                "policy_version": POLICY_VERSION,
                "evidence_condition": condition,
                "outcome_key": outcome_key,
                "requested_claim": claim_value,
                "request_count": 1,
                "expected_consequence": expected,
                "observed_consequence": observed,
                "failure_or_authorization_path": path,
            }
        )
    for request in outcomes["cross_construct_requests"]:
        requested_claim = request["requested_claim"]
        routes.append(
            {
                "route_id": hashlib.sha256(
                    f"{dataset_id}|cross-construct|{requested_claim}".encode()
                ).hexdigest()[:16],
                "policy_version": POLICY_VERSION,
                "evidence_condition": "cross-construct request",
                "outcome_key": "cross_construct_admission_rate",
                "requested_claim": requested_claim,
                "request_count": request["request_count"],
                "expected_consequence": request["expected_consequence"],
                "observed_consequence": request["observed_consequence"],
                "failure_or_authorization_path": "construct mismatch",
            }
        )
    return routes


def run_external_validation(root: Path) -> dict[str, Any]:
    external = root / "data" / "external"
    mrpc_paths = {
        split: external / f"mrpc_{split}.parquet"
        for split in ("train", "validation", "test")
    }
    paws_paths = {
        split: external / f"paws_{split}.parquet"
        for split in ("train", "validation", "test")
    }
    missing = [
        path
        for path in [
            *mrpc_paths.values(),
            *paws_paths.values(),
            external / "snli_1.0.zip",
            external / "al_cpl_11397eaa.zip",
            external / "torque_ab27019c.zip",
        ]
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing external policy stress-test inputs: "
            + ", ".join(map(str, missing))
        )
    datasets = {
        "mrpc": _summarize_paraphrase_dataset(
            "mrpc",
            "natural human-annotated paraphrase judgments",
            mrpc_paths,
            MRPC_MIRROR_URLS,
            (
                "MRPC terms are not stated in the GLUE mirror card; only aggregate "
                "statistics are redistributed here."
            ),
        ),
        "paws": _summarize_paraphrase_dataset(
            "paws-wiki-labeled-final",
            "adversarial high-overlap paraphrase judgments",
            paws_paths,
            PAWS_MIRROR_URLS,
            (
                "Google dataset terms permit use for any purpose and request source "
                "acknowledgement; mirror card consulted."
            ),
        ),
        "snli": _summarize_snli(external / "snli_1.0.zip"),
        "al_cpl": _summarize_al_cpl(external / "al_cpl_11397eaa.zip"),
        "torque": _summarize_torque(external / "torque_ab27019c.zip"),
    }
    for dataset_id, dataset in datasets.items():
        dataset["contract_routes"] = _contract_routes(
            dataset_id, dataset["contract_outcomes"]
        )
    return {
        "schema_version": "1.4",
        "policy_version": POLICY_VERSION,
        "evaluation_type": "external construct-matched policy stress testing",
        "scope": (
            "Externally produced annotations and dataset-derived labels stress-test "
            "evidence-to-claim matching only within their published constructs. Human "
            "annotations and preprocessing-derived labels are distinguished where the "
            "source archive permits; relation records are not treated as statistically "
            "independent samples. Results are not predictive trials, normative policy "
            "validation, or validation of excluded constructs."
        ),
        "datasets": datasets,
        "raw_text_redistributed": False,
    }
