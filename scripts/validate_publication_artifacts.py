"""Validate publication assets, source equality, privacy, and ACM compatibility."""

from __future__ import annotations

import ast
import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PIL import Image

from themegraph.admissibility import ClaimType
from themegraph.provenance import sha256_file
from themegraph.publication import (
    architecture_ablation_rows,
    build_publication_artifacts,
    claim_benchmark_rows,
    contract_necessity_rows,
    contract_property_rows,
    corpus_overview_rows,
    edge_distribution_rows,
    external_validation_rows,
    job_ads_quality_rows,
    policy_claim_rows,
    policy_lint_mutation_family_rows,
    policy_lint_mutation_rows,
    representation_enforcement_rows,
    specification_surface_rows,
    threshold_sensitivity_rows,
)
from themegraph.representation import COMPLETE_MEDIATION_ENTRY_POINTS

ROOT = Path(__file__).resolve().parents[1]

_CERTIFICATE_GUARDED_OUTPUT_MARKER = re.compile(
    r"^[ \t]*(?:#|//)\s*certificate-guarded-output-entry-point:\s*"
    r"(?P<identifier>[^;\r\n]+?)\s*;\s*guard=(?P<guard>[A-Za-z_$][\w$]*)\s*$",
    re.MULTILINE,
)
_PYTHON_SEMANTIC_EMITTER = re.compile(
    r"^(?:emit|render|serialize|export|governed)[a-z0-9_]*"
    r"(?:semantic|claim|representation|result|graph)[a-z0-9_]*$",
    re.IGNORECASE,
)
_JAVASCRIPT_SEMANTIC_EMITTER = re.compile(
    r"function\s+(?P<name>(?:emit|render|serialize|export)[A-Za-z0-9_$]*"
    r"(?:Semantic|Claim|Representation|Result|Graph|Certificate)[A-Za-z0-9_$]*)\s*\(",
    re.IGNORECASE,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object in {path}")
    return value


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _stringify_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def _validate_manuscript_statistics(root: Path, specification: dict[str, Any]) -> None:
    acmart = specification["corpora"]["acmart"]
    geometry = acmart["edge_set_geometry"]
    summary = acmart["survival_summary"]
    consequences = acmart["certificate_consequences"]
    expected = {
        "TGAcmtUnionEdges": f"{acmart['union_edge_count']:,}",
        "TGAcmtAuthorizedEdges": f"{consequences['admitted_union_edges']:,}",
        "TGAcmtQualifiedEdges": f"{consequences['qualified_union_edges']:,}",
        "TGAcmtIntersectionEdges": f"{geometry['intersection_count']:,}",
        "TGAcmtDefaultMeanPersistence": f"{summary['default_edge_mean']:.3f}",
        "TGAcmtComponentJaccard": f"{summary['component_overlap_mean']:.3f}",
    }
    macro_path = root / "artifacts" / "tables" / "manuscript_statistics.tex"
    macros = macro_path.read_text(encoding="ascii")
    manuscript = (root / "manuscript" / "themegraph_chi_2027.tex").read_text(
        encoding="utf-8"
    )
    if r"\input{../artifacts/tables/manuscript_statistics.tex}" not in manuscript:
        raise ValueError("Manuscript does not import authoritative statistics macros")
    for name, value in expected.items():
        declaration = f"\\newcommand{{\\{name}}}{{{value}}}"
        if declaration not in macros:
            raise ValueError(f"Authoritative manuscript statistic differs: {name}")
        if f"\\{name}" not in manuscript:
            raise ValueError(f"Authoritative manuscript statistic is unused: {name}")


def _validate_reason_and_route_taxonomy(
    benchmark: dict[str, Any], external: dict[str, Any]
) -> None:
    cases = {
        case["case_id"]: case["certificate"]
        for case in benchmark["claim_decisions"]["cases"]
    }
    duplicated = cases["duplicated-evidence"]
    expected_reasons = ["uncertainty-inadequate", "dependence-inadequate"]
    if duplicated.get("triggered_reasons") != expected_reasons:
        raise ValueError("Duplicated-evidence complete reason vector differs")
    if duplicated.get("decision_reason") != expected_reasons[0]:
        raise ValueError("Duplicated-evidence controlling reason differs")

    policy_version = benchmark["policy"]["policy_version"]
    if external.get("policy_version") != policy_version:
        raise ValueError("External route policy version differs from benchmark")
    torque = external["datasets"]["torque"]["contract_outcomes"]
    if torque.get("mention_order_triggered_reasons") != [
        "mention-order-insufficient"
    ]:
        raise ValueError("TORQUE mention-order route taxonomy differs")


def _validate_displayed_requested_claims(external: dict[str, Any]) -> None:
    declared_claims = {claim.value for claim in ClaimType}
    source_claims = {
        (dataset_id.upper().replace("_", "-"), route["evidence_condition"]): route[
            "requested_claim"
        ]
        for dataset_id, dataset in external["datasets"].items()
        for route in dataset["contract_routes"]
        if route["evidence_condition"] != "cross-construct request"
        if route["outcome_key"] in dataset["contract_outcomes"]
    }
    cross_construct = {
        dataset_id.upper().replace("_", "-"): [
            route
            for route in dataset["contract_routes"]
            if route["evidence_condition"] == "cross-construct request"
        ]
        for dataset_id, dataset in external["datasets"].items()
    }
    displayed_rows = external_validation_rows(external)
    if len(displayed_rows) != len(source_claims) + len(cross_construct):
        raise ValueError("Displayed external routes and source routes differ")
    for row in displayed_rows:
        key = (row["dataset"], row["evidence_condition"])
        if row["evidence_condition"] == "cross-construct request":
            routes = cross_construct[row["dataset"]]
            exact_claims = sorted(route["requested_claim"] for route in routes)
            if not routes or not set(exact_claims) <= declared_claims:
                raise ValueError("Cross-construct routes contain an undeclared claim")
            if row.get("requested_claim_types") != ", ".join(exact_claims):
                raise ValueError("Displayed aggregate differs from exact typed requests")
            if row.get("deterministic_request_count") != sum(
                route["request_count"] for route in routes
            ):
                raise ValueError("Cross-construct deterministic request count differs")
            if row.get("route_ids") != ", ".join(
                route["route_id"] for route in routes
            ):
                raise ValueError("Cross-construct route identifiers differ")
            continue
        if row["requested_claim"] != source_claims.get(key):
            raise ValueError(
                "Displayed requested claim differs from certificate/source route: "
                f"{key}"
            )


def _validate_permitted_statement_categories(benchmark: dict[str, Any]) -> None:
    expected = {
        "admit": "semantic claim",
        "prevalence-qualify": "qualified statistic",
        "conflict-qualify": "contested claim",
        "refuse-with-fallback": "fallback statement",
        "refuse-without-fallback": "refusal explanation",
    }
    observed = {
        row["state"]: row["permitted_statement"]
        for row in benchmark["representation_enforcement"]["states"]
    }
    if observed != expected:
        raise ValueError("Representation permitted-statement categories differ")


def _validate_manuscript_claim_identifiers(
    root: Path, benchmark: dict[str, Any]
) -> None:
    declared_claims = {claim["claim"] for claim in benchmark["policy"]["claims"]}
    manuscript = (root / "manuscript" / "themegraph_chi_2027.tex").read_text(
        encoding="utf-8"
    )
    extension = re.search(r"adding \\texttt\{([^}]+)\}", manuscript)
    if extension is None:
        raise ValueError("Manuscript lacks the serialized policy-extension claim ID")
    extension_claim = extension.group(1)
    if extension_claim not in declared_claims:
        raise ValueError(
            f"Manuscript uses undeclared policy-extension claim ID: {extension_claim}"
        )


def _semantic_output_source_paths(root: Path) -> list[Path]:
    return sorted((root / "src" / "themegraph").rglob("*.py")) + sorted(
        (root / "prototype").rglob("*.js")
    )


def _marker_immediately_precedes(
    source: str, markers: list[re.Match[str]], declaration_offset: int
) -> bool:
    return any(
        not source[marker.end() : declaration_offset].strip()
        for marker in markers
        if marker.end() <= declaration_offset
    )


def _discover_semantic_output_inventory(root: Path) -> set[str]:
    inventory: dict[str, Path] = {}
    for path in _semantic_output_source_paths(root):
        source = path.read_text(encoding="utf-8")
        markers = list(_CERTIFICATE_GUARDED_OUTPUT_MARKER.finditer(source))
        for index, marker in enumerate(markers):
            identifier = marker.group("identifier").strip()
            guard = marker.group("guard")
            if identifier in inventory:
                raise ValueError(f"Duplicate semantic-output entry point: {identifier}")
            segment_end = markers[index + 1].start() if index + 1 < len(markers) else len(source)
            segment = source[marker.end() : segment_end]
            if re.search(rf"\b{re.escape(guard)}\s*\(", segment) is None:
                raise ValueError(
                    f"Certificate mediation is absent from {identifier} in {path.name}"
                )
            inventory[identifier] = path

        if path.suffix == ".py":
            tree = ast.parse(source, filename=str(path))
            candidates = (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _PYTHON_SEMANTIC_EMITTER.match(node.name)
            )
            for candidate in candidates:
                declaration_offset = sum(
                    len(line) for line in source.splitlines(keepends=True)[: candidate.lineno - 1]
                )
                if not _marker_immediately_precedes(source, markers, declaration_offset):
                    raise ValueError(
                        f"Uninventoried semantic-output candidate: {candidate.name} in {path.name}"
                    )
        else:
            for candidate in _JAVASCRIPT_SEMANTIC_EMITTER.finditer(source):
                if not _marker_immediately_precedes(source, markers, candidate.start()):
                    raise ValueError(
                        "Uninventoried semantic-output candidate: "
                        f"{candidate.group('name')} in {path.name}"
                    )
    return set(inventory)


def _validate_complete_mediation(root: Path, benchmark: dict[str, Any]) -> None:
    coverage = benchmark.get("complete_mediation", {})
    expected = set(COMPLETE_MEDIATION_ENTRY_POINTS)
    discovered = _discover_semantic_output_inventory(root)
    if discovered != expected:
        raise ValueError("Source-derived complete-mediation inventory differs")
    if set(coverage.get("entry_points", [])) != expected:
        raise ValueError("Complete-mediation entry-point inventory differs")
    if coverage.get("entry_point_count") != len(COMPLETE_MEDIATION_ENTRY_POINTS):
        raise ValueError("Complete-mediation entry-point count differs")
    if not coverage.get("all_certificate_required"):
        raise ValueError("Complete-mediation coverage is not fail closed")


def _compile_acm_fragments(root: Path) -> None:
    compiler = shutil.which("pdflatex")
    if compiler is None:
        raise RuntimeError("pdflatex is required to validate ACM fragments")
    table_paths = sorted((root / "artifacts" / "tables").glob("*.tex"))
    figure_path = root / "artifacts" / "figures" / "job_ads_quality.pdf"
    with tempfile.TemporaryDirectory(dir=root) as temporary_directory:
        temporary_root = Path(temporary_directory)
        includes = "\n".join(
            f"\\input{{{path.as_posix()}}}" for path in table_paths
        )
        source = (
            "\\documentclass[manuscript,screen,review,anonymous]{acmart}\n"
            "\\begin{document}\n"
            "\\title{Artifact Validation}\n"
            "\\author{Anonymous}\n"
            "\\maketitle\n"
            f"{includes}\n"
            "\\begin{figure}[t]\n"
            "\\centering\n"
            f"\\includegraphics[width=\\linewidth]{{{figure_path.as_posix()}}}\n"
            "\\caption{Validation rendering.}\n"
            "\\end{figure}\n"
            "\\end{document}\n"
        )
        tex_path = temporary_root / "validation.tex"
        tex_path.write_text(source, encoding="ascii")
        environment = os.environ.copy()
        texinputs = str(root / "acmart-primary") + os.pathsep
        environment["TEXINPUTS"] = texinputs + environment.get("TEXINPUTS", "")
        result = subprocess.run(
            [compiler, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ACM fragment compilation failed:\n{result.stdout[-4000:]}")


def _compile_active_manuscript(root: Path) -> None:
    compiler = shutil.which("pdflatex")
    bibliography = shutil.which("bibtex")
    if compiler is None or bibliography is None:
        raise RuntimeError("pdflatex and bibtex are required to validate the manuscript")
    manuscript_root = root / "manuscript"
    source_path = manuscript_root / "themegraph_chi_2027.tex"
    environment = os.environ.copy()
    environment["TEXINPUTS"] = (
        str(root / "acmart-primary")
        + os.pathsep
        + environment.get("TEXINPUTS", "")
    )
    environment["BIBINPUTS"] = (
        str(manuscript_root)
        + os.pathsep
        + environment.get("BIBINPUTS", "")
    )
    with tempfile.TemporaryDirectory(dir=root) as temporary_directory:
        temporary_root = Path(temporary_directory)
        latex_command = [
            compiler,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={temporary_root}",
            source_path.name,
        ]
        first = subprocess.run(
            latex_command,
            cwd=manuscript_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if first.returncode != 0:
            raise RuntimeError(f"Active manuscript compilation failed:\n{first.stdout[-4000:]}")
        bibliography_result = subprocess.run(
            [bibliography, source_path.stem],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if bibliography_result.returncode != 0:
            raise RuntimeError(
                "Active manuscript bibliography failed:\n"
                f"{bibliography_result.stdout[-4000:]}"
            )
        if "Warning--" in bibliography_result.stdout:
            raise ValueError(
                "Active manuscript bibliography contains metadata warnings:\n"
                f"{bibliography_result.stdout[-4000:]}"
            )
        for _ in range(2):
            result = subprocess.run(
                latex_command,
                cwd=manuscript_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Active manuscript compilation failed:\n{result.stdout[-4000:]}"
                )
        log = (temporary_root / f"{source_path.stem}.log").read_text(
            encoding="utf-8", errors="replace"
        )
        forbidden = (
            "There were undefined references",
            "Citation `",
            "Reference `",
            "Overfull \\hbox",
        )
        violations = [
            line
            for line in log.splitlines()
            if any(marker in line for marker in forbidden)
        ]
        if violations:
            raise ValueError(
                "Active manuscript contains unresolved references or overflow:\n"
                + "\n".join(violations)
            )


def _validate_fonts(pdf_paths: list[Path]) -> None:
    inspector = shutil.which("pdffonts")
    if inspector is None:
        raise RuntimeError("pdffonts is required to validate embedded fonts")
    for path in pdf_paths:
        result = subprocess.run(
            [inspector, str(path)], capture_output=True, text=True, check=True
        )
        font_rows = result.stdout.splitlines()[2:]
        if not font_rows or any(" yes " not in f" {row} " for row in font_rows):
            raise ValueError(f"PDF font is not embedded in {path}")


def validate_publication_artifacts(root: Path = ROOT) -> dict[str, Any]:
    first = build_publication_artifacts(root)
    first_hashes = {item["path"]: item["sha256"] for item in first["outputs"]}
    second = build_publication_artifacts(root)
    second_hashes = {item["path"]: item["sha256"] for item in second["outputs"]}
    if first_hashes != second_hashes:
        raise ValueError("Publication outputs are not deterministic across clean rebuilds")

    manifest_path = root / "artifacts" / "manifest.json"
    manifest = _read_json(manifest_path)
    output_records = {item["path"]: item for item in manifest["outputs"]}
    artifact_files = {
        relative_path
        for artifact in manifest["artifacts"]
        for relative_path in artifact["files"]
    }
    if artifact_files != set(output_records):
        raise ValueError("Manifest artifact files and output records differ")

    for relative_path, record in output_records.items():
        path = root / relative_path
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing or empty artifact: {path}")
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"Hash mismatch for {path}")

    png_paths = sorted((root / "artifacts").rglob("*.png"))
    pdf_paths = sorted((root / "artifacts").rglob("*.pdf"))
    svg_paths = sorted((root / "artifacts").rglob("*.svg"))
    for path in png_paths:
        with Image.open(path) as image:
            dpi = image.info.get("dpi", (0.0, 0.0))
            is_source_crop = path.stem.startswith("inspector_policy27_") and path.stem.endswith("_crop")
            if min(dpi) < 599 or (not is_source_crop and min(image.size) < 1000):
                raise ValueError(f"PNG resolution is below publication standard: {path}")
    for path in pdf_paths:
        if not path.read_bytes().startswith(b"%PDF"):
            raise ValueError(f"Invalid PDF: {path}")
    for path in svg_paths:
        root_element = ElementTree.parse(path).getroot()
        if not root_element.tag.endswith("svg"):
            raise ValueError(f"Invalid SVG: {path}")
    _validate_fonts(pdf_paths)

    summary = _read_json(root / "results" / "research_evaluation_summary.json")
    audit = _read_json(root / "results" / "glassdoor_simplyhired_jobs_audit.json")
    benchmark = _read_json(root / "results" / "claim_admissibility_benchmark.json")
    specification = _read_json(root / "results" / "specification_surface.json")
    external = _read_json(root / "results" / "external_validation.json")
    _validate_manuscript_statistics(root, specification)
    _validate_reason_and_route_taxonomy(benchmark, external)
    _validate_displayed_requested_claims(external)
    _validate_permitted_statement_categories(benchmark)
    _validate_manuscript_claim_identifiers(root, benchmark)
    _validate_complete_mediation(root, benchmark)
    corpus_payloads = {
        name: _read_json(root / "results" / "evaluation_corpora" / f"{name}.json")
        for name in summary["corpora"]
    }
    expected_tables = {
        "corpus_overview.csv": corpus_overview_rows(summary),
        "job_ads_quality.csv": job_ads_quality_rows(audit),
        "threshold_sensitivity.csv": threshold_sensitivity_rows(summary),
        "edge_distributions.csv": edge_distribution_rows(corpus_payloads),
        "claim_admissibility_benchmark.csv": claim_benchmark_rows(benchmark),
        "contract_properties.csv": contract_property_rows(benchmark),
        "policy_claim_types.csv": policy_claim_rows(benchmark),
        "policy_lint_mutations.csv": policy_lint_mutation_rows(benchmark),
        "policy_lint_mutation_families.csv": policy_lint_mutation_family_rows(benchmark),
        "representation_enforcement.csv": representation_enforcement_rows(benchmark),
        "architecture_enforcement_ablation.csv": architecture_ablation_rows(benchmark),
        "contract_field_necessity.csv": contract_necessity_rows(benchmark),
        "external_validation.csv": external_validation_rows(external),
        "specification_surface.csv": specification_surface_rows(specification),
    }
    for filename, rows in expected_tables.items():
        actual = _csv_rows(root / "artifacts" / "tables" / filename)
        if actual != _stringify_rows(rows):
            raise ValueError(f"Generated table differs from source JSON: {filename}")

    artifact_root = root / "artifacts"
    if list(artifact_root.rglob("*.xlsx")):
        raise ValueError("Raw workbook content must not be copied into artifacts")
    for path in (artifact_root / "data").glob("*.json"):
        content = path.read_text(encoding="utf-8")
        if any(
            field in content
            for field in (
                '"excerpt"',
                '"sentence1"',
                '"sentence2"',
                '"passage"',
                '"question"',
                '"concept_pair"',
            )
        ):
            raise ValueError(f"Private source excerpt found in artifact data: {path}")
    boundary = manifest["data_boundary"]
    if (
        boundary["raw_job_ad_text_included"]
        or boundary["raw_external_sentence_text_included"]
        or boundary["labor_market_inference_supported"]
    ):
        raise ValueError("Manifest overstates the job-ad evidence boundary")

    _compile_acm_fragments(root)
    _compile_active_manuscript(root)
    report = {
        "schema_version": "1.0",
        "status": "passed",
        "checks": {
            "deterministic_rebuild": True,
            "manifest_hashes": True,
            "png_600_dpi": True,
            "pdf_parseable_and_fonts_embedded": True,
            "svg_parseable": True,
            "tables_equal_source_json": True,
            "reason_and_route_taxonomy": True,
            "displayed_requested_claims_equal_source_routes": True,
            "permitted_statement_categories": True,
            "manuscript_claim_identifiers": True,
            "complete_mediation_entry_points": True,
            "raw_job_ad_text_excluded": True,
            "raw_external_sentence_text_excluded": True,
            "acm_fragments_compile": True,
            "active_manuscript_compile": True,
        },
        "counts": {
            "artifacts": len(manifest["artifacts"]),
            "outputs": len(manifest["outputs"]),
            "png": len(png_paths),
            "pdf": len(pdf_paths),
            "svg": len(svg_paths),
        },
    }
    report_path = artifact_root / "VALIDATION_REPORT.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )
    report_relative = report_path.relative_to(root).as_posix()
    manifest["artifacts"].append(
        {
            "id": "report-artifact-validation",
            "kind": "validation",
            "files": [report_relative],
            "source_inputs": ["artifacts/manifest.json"],
            "status": "observed",
            "caption": "Executable publication artifact validation results.",
            "alt_text": "",
        }
    )
    manifest["outputs"].append(
        {
            "path": report_relative,
            "sha256": sha256_file(report_path),
            "bytes": report_path.stat().st_size,
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )
    return report


if __name__ == "__main__":
    result = validate_publication_artifacts()
    print(json.dumps(result, indent=2))