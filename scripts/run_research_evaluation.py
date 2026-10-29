"""Run deterministic multi-corpus evaluation and threshold sensitivity analysis."""

from __future__ import annotations

import argparse
import json
import platform
import sysconfig
import tracemalloc
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from themegraph.adapters import (
    DirectoryTextAdapter,
    ONetZipAdapter,
    XlsxJobAdsAdapter,
)
from themegraph.audit import audit_job_ads, write_audit
from themegraph.benchmark import complete_benchmark
from themegraph.evaluation import (
    adjusted_rand_index,
    community_baselines,
    directional_ablations,
    pairwise_partition_scores,
    structural_metrics,
    symmetrized_baseline,
    vector_clustering_baselines,
)
from themegraph.pipeline import analyze_documents, export_result
from themegraph.provenance import document_sequence_sha256, sha256_file
from themegraph.relations import ConditionalAssociationExtractor
from themegraph.synthetic import planted_cycle_corpus
from themegraph.text import RegexUnitExtractor

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "results" / "research_evaluation_summary.json"


def deduplicate_by_normalized_text(documents: list) -> list:
    unique_documents = []
    observed_text = set()
    for document in documents:
        normalized_text = " ".join(document.text.split())
        if normalized_text in observed_text:
            continue
        observed_text.add(normalized_text)
        unique_documents.append(document)
    return unique_documents


def analyze(name: str, documents: list, include_bigrams: bool = True) -> dict:
    tracemalloc.start()
    started = perf_counter()
    result = analyze_documents(
        documents,
        name,
        RegexUnitExtractor(include_bigrams=include_bigrams),
        ConditionalAssociationExtractor(),
    )
    elapsed_seconds = perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    export_result(result, ROOT / "results" / "evaluation_corpora" / f"{name}.json")
    return {
        "performance": {
            "core_wall_seconds": elapsed_seconds,
            "peak_python_allocation_bytes": peak_bytes,
        },
        "structural": structural_metrics(result),
        "symmetrized": symmetrized_baseline(result),
        "ablations": directional_ablations(result),
        "communities": community_baselines(result),
    }


def threshold_sweep(
    name: str,
    documents: list,
    include_bigrams: bool = True,
    completed_rows: list[dict] | None = None,
    checkpoint: object | None = None,
) -> list[dict]:
    rows = list(completed_rows or [])
    completed = {
        (row["min_confidence"], row["min_lift"])
        for row in rows
    }
    for confidence in (0.5, 0.65, 0.8):
        for lift in (1.0, 1.05, 1.25):
            if (confidence, lift) in completed:
                continue
            result = analyze_documents(
                documents,
                name,
                RegexUnitExtractor(include_bigrams=include_bigrams),
                ConditionalAssociationExtractor(min_confidence=confidence, min_lift=lift),
            )
            rows.append(
                {
                    "min_confidence": confidence,
                    "min_lift": lift,
                    **structural_metrics(result),
                }
            )
            if callable(checkpoint):
                checkpoint(rows)
    return sorted(rows, key=lambda row: (row["min_confidence"], row["min_lift"]))


def _write_summary(output: dict) -> None:
    SUMMARY_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def _arguments() -> tuple[set[str] | None, bool]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", action="append")
    parser.add_argument("--refresh-default", action="store_true")
    arguments = parser.parse_args()
    return (set(arguments.corpus) if arguments.corpus else None, arguments.refresh_default)


def main(
    selected_names: set[str] | None = None, refresh_default: bool = False
) -> None:
    synthetic_documents, synthetic_expected = planted_cycle_corpus()
    job_ads_path = ROOT / "glassdoor_simplyhired_jobs_data.xlsx"
    job_ads_metadata_path = ROOT / "glassdoor_simplyhired_jobs_data.metadata.json"
    job_ads_metadata = json.loads(job_ads_metadata_path.read_text(encoding="utf-8"))
    if sha256_file(job_ads_path) != job_ads_metadata["data_file_sha256"]:
        raise ValueError("Replacement job dataset does not match its metadata digest")
    write_audit(
        audit_job_ads(XlsxJobAdsAdapter(job_ads_path), job_ads_metadata),
        ROOT / "results" / "glassdoor_simplyhired_jobs_audit.json",
    )
    job_ads_documents = list(XlsxJobAdsAdapter(job_ads_path).documents())
    deduplicated_job_ads_documents = deduplicate_by_normalized_text(job_ads_documents)
    onet_path = ROOT / "data" / "external" / "db_30_3_text.zip"
    acmart_path = ROOT / "acmart-primary"
    stdlib_path = Path(sysconfig.get_path("stdlib"))
    corpora = {
        "synthetic": (
            synthetic_documents,
            False,
            {"kind": "synthetic", "seed": 2027},
        ),
        "glassdoor_simplyhired_jobs": (
            job_ads_documents,
            True,
            {
                "kind": "author-collected-job-dataset",
                "path": job_ads_path.relative_to(ROOT).as_posix(),
                "file_sha256": sha256_file(job_ads_path),
                "metadata_path": job_ads_metadata_path.relative_to(ROOT).as_posix(),
                "metadata_sha256": sha256_file(job_ads_metadata_path),
                "provenance_status": job_ads_metadata["provenance_status"],
                "redistribution_status": job_ads_metadata["redistribution_status"],
                "source_platforms": job_ads_metadata["source_platforms"],
                "temporal_coverage": job_ads_metadata["temporal_coverage"],
                "temporal_design": job_ads_metadata["temporal_design"],
                "intended_public_release_license": job_ads_metadata[
                    "intended_public_release_license"
                ],
                "public_release_status": job_ads_metadata["public_release_status"],
                "sampling_frame_status": job_ads_metadata["sampling_frame_status"],
                "source_platform_label_per_row": job_ads_metadata[
                    "source_platform_label_per_row"
                ],
                "deduplication": "none",
            },
        ),
        "glassdoor_simplyhired_jobs_unique_descriptions": (
            deduplicated_job_ads_documents,
            True,
            {
                "kind": "author-collected-job-dataset",
                "path": job_ads_path.relative_to(ROOT).as_posix(),
                "file_sha256": sha256_file(job_ads_path),
                "metadata_path": job_ads_metadata_path.relative_to(ROOT).as_posix(),
                "metadata_sha256": sha256_file(job_ads_metadata_path),
                "provenance_status": job_ads_metadata["provenance_status"],
                "redistribution_status": job_ads_metadata["redistribution_status"],
                "source_platforms": job_ads_metadata["source_platforms"],
                "temporal_coverage": job_ads_metadata["temporal_coverage"],
                "temporal_design": job_ads_metadata["temporal_design"],
                "intended_public_release_license": job_ads_metadata[
                    "intended_public_release_license"
                ],
                "public_release_status": job_ads_metadata["public_release_status"],
                "sampling_frame_status": job_ads_metadata["sampling_frame_status"],
                "source_platform_label_per_row": job_ads_metadata[
                    "source_platform_label_per_row"
                ],
                "deduplication": "exact normalized description text",
                "source_document_count": len(job_ads_documents),
                "removed_document_count": (
                    len(job_ads_documents) - len(deduplicated_job_ads_documents)
                ),
            },
        ),
        "onet_500": (
            list(
                ONetZipAdapter(onet_path, max_documents=500).documents()
            ),
            True,
            {
                "kind": "licensed-dataset",
                "path": onet_path.relative_to(ROOT).as_posix(),
                "file_sha256": sha256_file(onet_path),
                "dataset": "O*NET 30.3",
                "license": "CC BY 4.0",
                "source_url": "https://www.onetcenter.org/database.html",
            },
        ),
        "acmart": (
            list(DirectoryTextAdapter(acmart_path, max_documents=100).documents()),
            True,
            {
                "kind": "local-software-text",
                "path": acmart_path.relative_to(ROOT).as_posix(),
                "research_dataset": False,
            },
        ),
        "python_stdlib_100": (
            list(
                DirectoryTextAdapter(stdlib_path, max_documents=100).documents()
            ),
            True,
            {
                "kind": "installed-software-text",
                "path": str(stdlib_path),
                "research_dataset": False,
            },
        ),
    }
    if SUMMARY_PATH.exists():
        output = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    else:
        output = {"schema_version": "1.0", "seed": 2027, "corpora": {}}
    output["environment"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                package: version(package)
                for package in ("themegraph", "networkx", "scikit-learn", "numpy")
            },
    }
    output["corpora"].pop("job_ads_2000", None)
    output["claim_admissibility_benchmark"] = complete_benchmark()
    unknown = (selected_names or set()) - set(corpora)
    if unknown:
        raise ValueError(f"Unknown corpora: {sorted(unknown)}")
    for name, (documents, include_bigrams, source) in corpora.items():
        if selected_names is not None and name not in selected_names:
            continue
        existing = output["corpora"].get(name, {})
        corpus_output = {
            "source": {
                **source,
                "consumed_document_count": len(documents),
                "document_sequence_sha256": document_sequence_sha256(documents),
            },
            "default": (
                analyze(name, documents, include_bigrams)
                if refresh_default
                else existing.get("default") or analyze(name, documents, include_bigrams)
            ),
            "threshold_sweep": existing.get("threshold_sweep", []),
        }
        output["corpora"][name] = corpus_output
        _write_summary(output)

        def checkpoint(rows: list[dict], current_output: dict = corpus_output) -> None:
            current_output["threshold_sweep"] = rows
            _write_summary(output)

        corpus_output["threshold_sweep"] = threshold_sweep(
            name,
            documents,
            include_bigrams,
            corpus_output["threshold_sweep"],
            checkpoint,
        )
        _write_summary(output)

    synthetic_result = analyze_documents(
        synthetic_documents,
        "synthetic",
        RegexUnitExtractor(include_bigrams=False),
        ConditionalAssociationExtractor(),
    )
    output["synthetic_labeled_baselines"] = {
        name: {
            "adjusted_rand_index": adjusted_rand_index(labels, synthetic_expected),
            "pairwise": pairwise_partition_scores(labels, synthetic_expected),
        }
        for name, labels in vector_clustering_baselines(
            synthetic_result, n_clusters=3
        ).items()
    }

    _write_summary(output)


if __name__ == "__main__":
    selected_corpora, refresh = _arguments()
    main(selected_corpora, refresh_default=refresh)
