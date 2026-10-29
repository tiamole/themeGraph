"""Command-line interface for audits, analyses, and synthetic benchmarks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from themegraph.adapters import DirectoryTextAdapter, XlsxJobAdsAdapter
from themegraph.audit import audit_job_ads, write_audit
from themegraph.evaluation import (
    adjusted_rand_index,
    pairwise_partition_scores,
    partition_labels,
    structural_metrics,
    symmetrized_baseline,
)
from themegraph.pipeline import analyze_documents, export_result
from themegraph.relations import ConditionalAssociationExtractor
from themegraph.synthetic import planted_cycle_corpus
from themegraph.text import RegexUnitExtractor


def _write_json(value: object, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="themegraph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit-job-ads")
    audit.add_argument("workbook")
    audit.add_argument("output")

    jobs = subparsers.add_parser("analyze-job-ads")
    jobs.add_argument("workbook")
    jobs.add_argument("output")
    jobs.add_argument("--max-documents", type=int, default=2000)

    directory = subparsers.add_parser("analyze-directory")
    directory.add_argument("root")
    directory.add_argument("output")
    directory.add_argument("--max-documents", type=int, default=100)

    benchmark = subparsers.add_parser("benchmark-synthetic")
    benchmark.add_argument("output")
    return parser


# certificate-guarded-output-entry-point: CLI structural export; guard=export_result
def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "audit-job-ads":
        write_audit(audit_job_ads(XlsxJobAdsAdapter(arguments.workbook)), arguments.output)
        return 0

    if arguments.command == "analyze-job-ads":
        adapter = XlsxJobAdsAdapter(arguments.workbook, arguments.max_documents)
        result = analyze_documents(adapter.documents(), "electrical-engineering-job-ads")
        export_result(result, arguments.output)
        return 0

    if arguments.command == "analyze-directory":
        adapter = DirectoryTextAdapter(arguments.root, max_documents=arguments.max_documents)
        result = analyze_documents(adapter.documents(), Path(arguments.root).name)
        export_result(result, arguments.output)
        return 0

    documents, expected = planted_cycle_corpus()
    result = analyze_documents(
        documents,
        "synthetic-planted-cycles",
        unit_extractor=RegexUnitExtractor(include_bigrams=False),
        relation_extractor=ConditionalAssociationExtractor(
            min_term_units=3,
            min_pair_units=3,
            min_confidence=0.65,
            min_lift=1.05,
            max_vocabulary=100,
        ),
    )
    predicted = partition_labels(result.components)
    payload = {
        "structural": structural_metrics(result),
        "pairwise": pairwise_partition_scores(predicted, expected),
        "adjusted_rand_index": adjusted_rand_index(predicted, expected),
        "symmetrized_baseline": symmetrized_baseline(result),
        "analysis": result.as_dict(),
    }
    _write_json(payload, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
