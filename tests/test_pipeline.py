import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from themegraph.adapters import ONetZipAdapter, XlsxJobAdsAdapter
from themegraph.audit import audit_job_ads
from themegraph.evaluation import (
    adjusted_rand_index,
    directional_ablations,
    partition_labels,
    structural_metrics,
)
from themegraph.models import DocumentRecord, TextUnit
from themegraph.pipeline import analyze_documents, export_result
from themegraph.relations import ConditionalAssociationExtractor
from themegraph.representation import (
    export_requested_claim,
    governed_representation,
)
from themegraph.synthetic import planted_cycle_corpus
from themegraph.text import RegexUnitExtractor


def test_conditional_association_preserves_meaningful_asymmetry():
    units = [
        TextUnit(f"u{index}", f"d{index}", "rare common", frozenset({"rare", "common"}))
        for index in range(3)
    ]
    units.extend(
        TextUnit(f"u{index}", f"d{index}", "common", frozenset({"common"}))
        for index in range(3, 10)
    )
    extractor = ConditionalAssociationExtractor(
        min_term_units=1, min_pair_units=2, min_confidence=0.6, min_lift=1.0
    )

    _, edges = extractor.extract(units)
    edge_pairs = {(edge.source, edge.target) for edge in edges}

    assert ("rare", "common") in edge_pairs
    assert ("common", "rare") not in edge_pairs
    edge = edges[0]
    assert edge.support == 3
    assert edge.document_support == 3
    assert edge.source_support == 0
    assert edge.effective_support_lower_bound == 0


def test_pipeline_recovers_planted_cycle_groups():
    documents, expected = planted_cycle_corpus()
    result = analyze_documents(
        documents,
        "synthetic",
        RegexUnitExtractor(include_bigrams=False),
        ConditionalAssociationExtractor(
            min_term_units=3,
            min_pair_units=3,
            min_confidence=0.65,
            min_lift=1.05,
            max_vocabulary=100,
        ),
    )
    predicted = partition_labels(result.components)

    assert adjusted_rand_index(predicted, expected) == 1.0
    assert structural_metrics(result)["nontrivial_scc_count"] == 3
    assert structural_metrics(result)["asymmetric_edge_rate"] > 0
    certificates = {
        item["claim_type"]: item for item in result.as_dict()["claim_certificates"]
    }
    assert certificates["lexical-association"]["decision"] == "ADMIT"
    assert certificates["asymmetric-conditional"]["decision"] == "QUALIFY"
    assert certificates["causal-influence"]["decision"] == "REFUSE"
    assert certificates["causal-influence"]["fallback_claim"] is None
    ablations = directional_ablations(result)
    assert ablations["reverse_all_edges"]["partition_unchanged"] is True
    assert ablations["remove_all_relations_no_scc"]["largest_component"] == 1


def test_empty_documents_produce_an_empty_analysis():
    result = analyze_documents([DocumentRecord("empty", "")], "empty")

    assert result.document_count == 1
    assert result.unit_count == 0
    assert result.nodes == []
    assert result.edges == []
    payload = json.loads(json.dumps(result.as_dict()))
    assert payload["corpus_name"] == "empty"
    assert payload["schema_version"] == "2.0"
    assert all(
        certificate["decision"] == "REFUSE"
        for certificate in payload["claim_certificates"]
    )


def test_semantic_outputs_require_a_valid_authorizing_certificate(tmp_path: Path) -> None:
    result = analyze_documents(
        [DocumentRecord("document", "alpha beta", provenance="fixture")],
        "fixture",
    )

    lexical = governed_representation(result, "lexical-association")
    assert lexical["visual_encoding"] == "undirected-link"
    assert lexical["requested_claim_export_allowed"] is True
    export_requested_claim(result, tmp_path / "lexical.json", "lexical-association")

    causal = governed_representation(result, "causal-influence")
    assert causal["visual_encoding"] == "no-relation"
    assert causal["edges"] == []
    with pytest.raises(PermissionError):
        export_requested_claim(result, tmp_path / "causal.json", "causal-influence")


def test_semantic_outputs_fail_closed_for_missing_unknown_or_malformed_certificates(
    tmp_path: Path,
) -> None:
    result = analyze_documents(
        [DocumentRecord("document", "alpha beta", provenance="fixture")],
        "fixture",
    )
    with pytest.raises(ValueError):
        governed_representation(result, "not-a-declared-claim")

    missing = deepcopy(result)
    missing.claim_certificates = []
    with pytest.raises(ValueError):
        governed_representation(missing, "lexical-association")
    with pytest.raises(ValueError):
        export_result(missing, tmp_path / "structural.json")

    malformed = deepcopy(result)
    certificate = next(
        item
        for item in malformed.claim_certificates
        if item["claim_type"] == "causal-influence"
    )
    certificate["allowed_encoding"] = "directed-arrow"
    with pytest.raises(ValueError):
        governed_representation(malformed, "causal-influence")


def test_unitization_modes_change_the_observation_surface() -> None:
    documents = [
        DocumentRecord(
            "document",
            "Alpha methods. Beta results.\n\nGamma discussion.",
            provenance="fixture",
        )
    ]

    sentence_units = RegexUnitExtractor(
        unit_mode="sentence", include_bigrams=False
    ).extract(documents)
    paragraph_units = RegexUnitExtractor(
        unit_mode="paragraph", include_bigrams=False
    ).extract(documents)
    window_units = RegexUnitExtractor(
        unit_mode="sentence-window", include_bigrams=False
    ).extract(documents)

    assert len(sentence_units) == 3
    assert len(paragraph_units) == 2
    assert len(window_units) == 2
    assert {"alpha", "methods", "beta", "results"} <= window_units[0].terms


def _write_inline_xlsx(path: Path) -> None:
    rows = [
        ["Job Title", "Company Name", "Location", "Description", "Skills"],
        ["Engineer", "Company", "City", "Control systems", "Control systems"],
        ["Engineer", "Company", "City", "Control systems", "Control systems"],
        ["Technician", "", "Town", "Safety testing", "Inspection"],
    ]
    xml_rows = []
    for row_index, row in enumerate(rows, 1):
        cells = []
        for column_index, value in enumerate(row):
            column = chr(ord("A") + column_index)
            cells.append(
                f'<c r="{column}{row_index}" t="inlineStr"><is><t>{value}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def test_xlsx_adapter_and_audit_handle_duplicates_and_empty_cells(tmp_path):
    workbook = tmp_path / "jobs.xlsx"
    _write_inline_xlsx(workbook)
    adapter = XlsxJobAdsAdapter(workbook)

    documents = list(adapter.documents())
    audit = audit_job_ads(adapter)

    assert len(documents) == 3
    assert documents[0].text == "Control systems"
    assert documents[2].metadata["company_name"] == ""
    assert documents[2].text == "Safety testing\nInspection"
    assert audit["exact_duplicate_row_instances"] == 1
    assert audit["description_skills_equal_count"] == 2
    assert audit["null_counts"]["Company Name"] == 1


def test_onet_zip_adapter_joins_tasks_by_occupation_code(tmp_path):
    archive_path = tmp_path / "onet.zip"
    occupations = (
        "O*NET-SOC Code\tTitle\tDescription\n"
        "11-0000.00\tFirst occupation\tFirst description.\n"
        "22-0000.00\tSecond occupation\tSecond description.\n"
    )
    tasks = (
        "O*NET-SOC Code\tTask ID\tTask\n"
        "11-0000.00\t1\tPlan work.\n"
        "11-0000.00\t2\tReview work.\n"
        "22-0000.00\t3\tTest work.\n"
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(ONetZipAdapter.occupation_entry, occupations)
        archive.writestr(ONetZipAdapter.task_entry, tasks)

    documents = list(ONetZipAdapter(archive_path).documents())

    assert [document.document_id for document in documents] == [
        "11-0000.00",
        "22-0000.00",
    ]
    assert documents[0].text == "First description.\nPlan work.\nReview work."
    assert documents[1].metadata["occupation_title"] == "Second occupation"
    assert "CC BY 4.0" in documents[0].provenance