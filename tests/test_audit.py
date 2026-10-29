from __future__ import annotations

from collections.abc import Iterator

from themegraph.audit import audit_job_ads


class FourColumnAdapter:
    expected_columns = ("Job Title", "Company Name", "Location", "Description", "Skills")
    path = "fixture.xlsx"

    def raw_rows(self) -> Iterator[dict[str, str]]:
        yield {
            "Job Title": "Engineer",
            "Company Name": "Example",
            "Location": "Logan",
            "Description": "Build systems",
        }
        yield {
            "Job Title": "Engineer",
            "Company Name": "Example",
            "Location": "Logan",
            "Description": "Build systems",
        }


def test_audit_reports_absent_optional_fields_without_inventing_missing_values() -> None:
    metadata = {
        "provenance_status": "author_attested_file_supported_in_part",
        "redistribution_status": "planned_not_yet_verified_by_public_deposit",
    }

    result = audit_job_ads(FourColumnAdapter(), metadata)  # type: ignore[arg-type]

    assert result["row_count"] == 2
    assert result["columns"] == ["Job Title", "Company Name", "Location", "Description"]
    assert result["missing_expected_columns"] == ["Skills"]
    assert "Skills" not in result["null_counts"]
    assert result["description_skills_comparable"] is False
    assert result["description_skills_equal_rate"] is None
    assert result["source_platform_column_present"] is False
    assert result["exact_duplicate_description_instances"] == 1
    assert result["provenance_status"] == "author_attested_file_supported_in_part"