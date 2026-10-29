"""Structured audits for the electrical engineering job advertisement workbook."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from themegraph.adapters import XlsxJobAdsAdapter


def _digest(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def audit_job_ads(
    adapter: XlsxJobAdsAdapter, dataset_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    row_hashes: Counter[str] = Counter()
    description_hashes: Counter[str] = Counter()
    null_counts: Counter[str] = Counter()
    whitespace_changed: Counter[str] = Counter()
    unique_values: dict[str, set[str]] = {}
    text_lengths: dict[str, list[int]] = {}
    description_skills_equal = 0
    row_count = 0
    columns: list[str] = []

    for row in adapter.raw_rows():
        if not columns:
            columns = list(row)
            null_counts.update({column: 0 for column in columns})
            whitespace_changed.update({column: 0 for column in columns})
            unique_values = {column: set() for column in columns}
            text_lengths = {
                column: [] for column in ("Description", "Skills") if column in columns
            }
        row_count += 1
        raw_values = [row.get(column, "") for column in columns]
        normalized_values = [value.strip() for value in raw_values]
        row_hashes[_digest(normalized_values)] += 1
        description = row.get("Description", "").strip()
        if "Description" in columns:
            description_hashes[_digest([description])] += 1

        for column, raw, normalized in zip(
            columns, raw_values, normalized_values, strict=True
        ):
            if not normalized:
                null_counts[column] += 1
            if raw != normalized:
                whitespace_changed[column] += 1
            unique_values[column].add(normalized)

        for field in text_lengths:
            text_lengths[field].append(len(row.get(field, "").strip()))
        if (
            "Description" in columns
            and "Skills" in columns
            and description == row.get("Skills", "").strip()
        ):
            description_skills_equal += 1

    def duplicate_instances(counter: Counter[str]) -> int:
        return sum(count - 1 for count in counter.values() if count > 1)

    skills_comparable = "Description" in columns and "Skills" in columns
    platform_columns = {
        column
        for column in columns
        if column.casefold() in {"platform", "source", "source platform", "job platform"}
    }
    metadata = dataset_metadata or {}
    result = {
        "source": str(adapter.path),
        "row_count": row_count,
        "columns": columns,
        "expected_columns": list(adapter.expected_columns),
        "missing_expected_columns": [
            column for column in adapter.expected_columns if column not in columns
        ],
        "null_counts": dict(null_counts),
        "null_rates": {
            column: count / row_count if row_count else 0.0
            for column, count in null_counts.items()
        },
        "whitespace_changed_counts": dict(whitespace_changed),
        "unique_counts": {
            column: len(values) for column, values in unique_values.items()
        },
        "exact_duplicate_row_instances": duplicate_instances(row_hashes),
        "exact_duplicate_description_instances": duplicate_instances(description_hashes),
        "description_skills_comparable": skills_comparable,
        "description_skills_equal_count": (
            description_skills_equal if skills_comparable else None
        ),
        "description_skills_equal_rate": (
            description_skills_equal / row_count
            if row_count and skills_comparable
            else None
        ),
        "source_platform_column_present": bool(platform_columns),
        "source_platform_columns": sorted(platform_columns),
        "text_length_summary": {
            field: {
                "minimum": min(values, default=0),
                "median": median(values) if values else 0,
                "p95": _percentile(values, 0.95),
                "maximum": max(values, default=0),
            }
            for field, values in text_lengths.items()
        },
        "provenance_status": metadata.get("provenance_status", "unverified"),
        "redistribution_status": metadata.get("redistribution_status", "unverified"),
        "dataset_metadata": metadata,
    }
    return result


def write_audit(audit: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2, ensure_ascii=True), encoding="utf-8")
