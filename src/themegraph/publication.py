"""Generate publication artifacts from validated machine-readable results."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib
from matplotlib.figure import Figure
from matplotlib.image import imread
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.ticker import LogLocator, NullFormatter, PercentFormatter
from PIL import Image

from themegraph.admissibility import POLICY_VERSION
from themegraph.provenance import sha256_file

matplotlib.use("Agg")
matplotlib.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 7.5,
        "font.weight": "regular",
        "axes.titlesize": 8.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 7.5,
        "axes.labelcolor": "#233240",
        "axes.edgecolor": "#233240",
        "axes.linewidth": 0.7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.facecolor": "#FFFFFF",
        "figure.facecolor": "#FFFFFF",
        "savefig.facecolor": "#FFFFFF",
        "xtick.color": "#465563",
        "ytick.color": "#465563",
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "lines.linewidth": 1.4,
        "lines.markersize": 4.5,
        "patch.linewidth": 0.7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.hashsalt": "themegraph-chi-2027",
    }
)


PALETTE = {
    "ink": "#152536",
    "blue": "#2B6F9C",
    "teal": "#258A7C",
    "gold": "#C9912E",
    "vermilion": "#BB5138",
    "slate": "#607284",
    "gray": "#7A8793",
    "line": "#C9D1D8",
    "mist": "#EEF3F6",
    "blue_pale": "#E5F0F6",
    "teal_pale": "#E5F2EF",
    "gold_pale": "#F7EEDB",
    "red_pale": "#F6E8E3",
    "red": "#BB5138",
    "green": "#258A7C",
    "orange": "#C9912E",
}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return value


def corpus_overview_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, corpus in summary["corpora"].items():
        structural = corpus["default"]["structural"]
        performance = corpus["default"]["performance"]
        rows.append(
            {
                "corpus": name,
                "documents": structural["documents"],
                "units": structural["units"],
                "nodes": structural["nodes"],
                "edges": structural["edges"],
                "scc_count": structural["scc_count"],
                "largest_scc": structural["largest_scc"],
                "singleton_rate": structural["singleton_rate"],
                "asymmetric_edge_rate": structural["asymmetric_edge_rate"],
                "wall_seconds": performance["core_wall_seconds"],
                "peak_mib": performance["peak_python_allocation_bytes"] / 1024**2,
            }
        )
    return rows


def job_ads_quality_rows(audit: dict[str, Any]) -> list[dict[str, Any]]:
    row_count = audit["row_count"]
    return [
        {
            "measure": "Description missing",
            "count": audit["null_counts"]["Description"],
            "rate": audit["null_rates"]["Description"],
        },
        {
            "measure": "Duplicate rows beyond first instance",
            "count": audit["exact_duplicate_row_instances"],
            "rate": audit["exact_duplicate_row_instances"] / row_count,
        },
        {
            "measure": "Duplicate descriptions beyond first instance",
            "count": audit["exact_duplicate_description_instances"],
            "rate": audit["exact_duplicate_description_instances"] / row_count,
        },
    ]


def _corpus_label(name: str) -> str:
    return {
        "synthetic": "Synthetic",
        "glassdoor_simplyhired_jobs": "Jobs: all rows",
        "glassdoor_simplyhired_jobs_unique_descriptions": "Jobs: unique descriptions",
        "onet_500": "O*NET",
        "acmart": "ACM text",
        "python_stdlib_100": "Python stdlib",
    }.get(name, name.replace("_", " "))


def threshold_sensitivity_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, corpus in summary["corpora"].items():
        for result in corpus.get("threshold_sweep", []):
            rows.append(
                {
                    "corpus": name,
                    "min_confidence": result["min_confidence"],
                    "min_lift": result["min_lift"],
                    "edges": result["edges"],
                    "scc_count": result["scc_count"],
                    "largest_scc": result["largest_scc"],
                    "singleton_rate": result["singleton_rate"],
                    "asymmetric_edge_rate": result["asymmetric_edge_rate"],
                }
            )
    return rows


def threshold_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["corpus"], row["min_confidence"]), []).append(row)
    compact_rows = []
    for (corpus, confidence), group in grouped.items():
        signatures = {
            (row["edges"], row["scc_count"], row["largest_scc"]) for row in group
        }
        if len(signatures) != 1:
            compact_rows.extend(
                {
                    "corpus": row["corpus"],
                    "min_confidence": row["min_confidence"],
                    "lift_range": f'{row["min_lift"]:.2f}',
                    "edges": row["edges"],
                    "scc_count": row["scc_count"],
                    "largest_scc": row["largest_scc"],
                }
                for row in group
            )
            continue
        edges, scc_count, largest_scc = signatures.pop()
        compact_rows.append(
            {
                "corpus": corpus,
                "min_confidence": confidence,
                "lift_range": "1.00 to 1.25",
                "edges": edges,
                "scc_count": scc_count,
                "largest_scc": largest_scc,
            }
        )
    return compact_rows


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def edge_distribution_rows(
    corpus_payloads: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for name, payload in corpus_payloads.items():
        edges = payload.get("edges", [])
        if not edges:
            continue
        confidence = [float(edge["confidence"]) for edge in edges]
        support = [float(edge["support"]) for edge in edges]
        lift = [float(edge["lift"]) for edge in edges]
        evidence = [float(len(edge.get("evidence", []))) for edge in edges]
        rows.append(
            {
                "corpus": name,
                "edge_count": len(edges),
                "confidence_p25": _percentile(confidence, 0.25),
                "confidence_median": median(confidence),
                "confidence_p75": _percentile(confidence, 0.75),
                "support_p25": _percentile(support, 0.25),
                "support_median": median(support),
                "support_p75": _percentile(support, 0.75),
                "lift_p25": _percentile(lift, 0.25),
                "lift_median": median(lift),
                "lift_p75": _percentile(lift, 0.75),
                "shown_evidence_median": median(evidence),
            }
        )
    return rows


def claim_benchmark_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    def displayed_witness(case: dict[str, Any]) -> str:
        full_witness = "; ".join(case["certificate"].get("witness", []))
        replacements = {
            "All required evidence and policy gates passed.": "All gates passed",
            "Orientation is determined by marginal prevalence, not directional observation.": "Prevalence-derived orientation",
            "Missing required evidence alternative: event-order OR annotation-temporal-precedence.": "Missing event-order evidence",
            "Missing required evidence alternative: causal-identification.": "Missing causal-identification evidence",
            "The observed persistence S=0.650 does not meet gate=0.800.": "S=0.650 < gate=0.800",
            "Uncertainty evidence is inadequate for identification.; Dependence-aware resampling is not established.": "Uncertainty inadequate; dependence resampling absent",
            "Construct-matched conflict: support: A precedes B; counterevidence: B precedes A.": "Opposing matched temporal annotations",
            "Required provenance fields are incomplete for the intended claim.": "Required provenance incomplete",
        }
        return replacements.get(full_witness, full_witness or "All gates passed")

    return [
        {
            "case": case["case_id"],
            "claim": case["certificate"]["claim_type"],
            "expected": case["expected_decision"],
            "observed": case["certificate"]["decision"],
            "encoding": case["certificate"]["allowed_encoding"],
            "fallback": case["certificate"]["fallback_claim"] or "none",
            "observed_evidence": ", ".join(
                case["certificate"].get("observed_channels", [])
            ) or "none",
            "triggered_reasons": ", ".join(
                case["certificate"].get(
                    "triggered_reasons",
                    case["certificate"].get("reason_codes", []),
                )
            ) or "none",
            "decision_reason": case["certificate"].get("decision_reason") or "none",
            "requested_claim_export": (
                "allowed" if case["certificate"].get("allowed_export") else "blocked"
            ),
            "witness": displayed_witness(case),
            "remediation": "; ".join(
                case["certificate"].get("remediation", [])
            ) or "none",
        }
        for case in benchmark["claim_decisions"]["cases"]
    ]


def policy_claim_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    def fallback_summary(claim: dict[str, Any]) -> str:
        projections = {
            projection["target_claim"]: projection["projection_id"]
            for projection in claim.get("fallback_projections", [])
        }
        missing = set(claim["fallback_preferences"]) - projections.keys()
        if missing:
            raise ValueError(
                f"Missing fallback projections for {claim['claim']}: {sorted(missing)}"
            )
        return ", ".join(
            f"{fallback} via {projections[fallback]}"
            for fallback in claim["fallback_preferences"]
        ) or "none"

    return [
        {
            "family": claim.get("claim_family", "unclassified"),
            "claim": claim["claim"],
            "object_signatures": " OR ".join(
                f"{source}->{target}"
                for source, target in claim.get("object_signatures", [])
            ) or "untyped",
            "sufficient_predicate": " OR ".join(
                predicate["description"] for predicate in claim["evidence_predicates"]
            ),
            "scope": claim.get("scope_semantics", "unscoped"),
            "adjudication": (
                "approved review required"
                if any(
                    predicate.get("requires_approved_adjudication", False)
                    for predicate in claim["evidence_predicates"]
                )
                else "not required"
            ),
            "conflict": claim["on_counterevidence"],
            "encoding": claim["encoding"],
            "fallback": fallback_summary(claim),
        }
        for claim in benchmark["policy"]["claims"]
    ]


def policy_lint_mutation_family_rows(
    benchmark: dict[str, Any],
) -> list[dict[str, Any]]:
    family_by_mutation = {
        "remove-claim-declaration": "declaration / schema",
        "unreachable-predicate": "declaration / schema",
        "duplicate-predicate": "declaration / schema",
        "remove-remediation": "declaration / schema",
        "generic-order-substitution": "evidence typing",
        "generic-reference-substitution": "evidence typing",
        "omit-object-signature": "evidence typing",
        "omit-causal-estimand": "causal / interpretive adjudication",
        "omit-theme-adjudication": "causal / interpretive adjudication",
        "omit-causal-adjudication": "causal / interpretive adjudication",
        "intervention-as-causal-alternative": "causal / interpretive adjudication",
        "omit-analyst-comparator": "causal / interpretive adjudication",
        "fallback-cycle": "fallback / projection",
        "undeclared-fallback-target": "fallback / projection",
        "unscoped-to-pair-fallback": "fallback / projection",
        "omit-fallback-projection": "fallback / projection",
        "mistype-fallback-projection": "fallback / projection",
        "drop-fallback-projection-provenance": "fallback / projection",
        "allow-refused-export": "representation / export",
        "collapse-statistical-semantic-encoding": "representation / export",
        "behaviorally-identical-version": "semantic versioning",
    }
    mutations = benchmark.get("policy_lint_mutations", {}).get("mutations", [])
    grouped: dict[str, list[dict[str, Any]]] = {}
    for mutation in mutations:
        grouped.setdefault(family_by_mutation[mutation["mutation_id"]], []).append(
            mutation
        )
    return [
        {
            "mutation_family": family,
            "targeted_mutations": len(rows),
            "detected": sum(bool(row["detected"]) for row in rows),
            "result": (
                "all detected" if all(row["detected"] for row in rows) else "detection failure"
            ),
            "artifact_detail": "row-level trigger vectors retained",
        }
        for family, rows in grouped.items()
    ]


def policy_lint_mutation_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "mutation": mutation["mutation_id"],
            "intended_check": mutation["intended_check"].replace("_", " "),
            "detected": "yes" if mutation["detected"] else "no",
            "additional_failure_count": mutation.get("additional_failure_count", 0),
            "additional_failed_checks": ", ".join(
                check.replace("_", " ")
                for check in mutation.get("additional_failed_checks", [])
            ) or "none",
            "exact_localization": "yes" if mutation.get("exact_localization") else "no",
        }
        for mutation in benchmark.get("policy_lint_mutations", {}).get("mutations", [])
    ]


def representation_enforcement_rows(
    benchmark: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "state": row["state"],
            "decision": row["decision"],
            "decision_reason": row["decision_reason"],
            "permitted_statement": row["permitted_statement"],
            "mark": row["mark"],
            "requested_claim_export": row["requested_claim_export"],
            "fallback": row["fallback"],
            "witness": row["witness"],
            "remediation": row["remediation"],
            "conforms": "yes" if row["conforms"] else "no",
        }
        for row in benchmark.get("representation_enforcement", {}).get("states", [])
    ]


def architecture_ablation_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "architecture": row["architecture"],
            "fixtures": row["fixture_count"],
            "unauthorized_statements": (
                f'{row["unauthorized_statements_emitted"]}/{row["fixture_count"]}'
            ),
            "unauthorized_marks": (
                f'{row["unauthorized_semantic_marks_emitted"]}/{row["fixture_count"]}'
            ),
            "unauthorized_exports": (
                f'{row["unauthorized_requested_exports_emitted"]}/{row["fixture_count"]}'
            ),
            "lawful_fallbacks": (
                f'{row["lawful_fallbacks_preserved"]}/{row["fixture_count"]}'
            ),
        }
        for row in benchmark.get("architecture_enforcement_ablation", {}).get(
            "architectures", []
        )
    ]


def contract_necessity_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "contract_distinction": row["distinction"],
            "removal_probe": row["probe_id"],
            "invalid_behavior_enabled": row["invalid_behavior_enabled"],
            "joint_control_consequence": row["contribution_consequence"],
            "detected": "yes" if row["detected"] else "no",
        }
        for row in benchmark.get("contract_field_necessity", {}).get("rows", [])
    ]


def contract_property_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    properties = benchmark["contract_properties"]
    falsification = {
        row["property"].replace("-", " "): row
        for row in properties["falsification_matrix"]
    }
    return [
        {
            "property": name.replace("_", " "),
            "perturbation": falsification[name.replace("_", " ")]["perturbation"],
            "failure_condition": falsification[name.replace("_", " ")][
                "failure_condition"
            ],
            "passed": "yes" if passed else "no",
        }
        for name, passed in properties["checks"].items()
    ]


def external_validation_rows(validation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, dataset in validation["datasets"].items():
        outcomes = dataset["contract_outcomes"]
        cross_construct_routes = []
        for route in dataset["contract_routes"]:
            outcome_key = route["outcome_key"]
            if outcome_key not in outcomes:
                continue
            if route["evidence_condition"] == "cross-construct request":
                cross_construct_routes.append(route)
                continue
            value = outcomes[outcome_key]
            expected = route["expected_consequence"]
            expected_value = (
                1.0
                if outcome_key.endswith("_refusal_rate") or expected == "ADMIT"
                else 0.0
            )
            rows.append(
                {
                    "dataset": name.upper().replace("_", "-"),
                    "evidence_condition": route["evidence_condition"],
                    "requested_claim": route["requested_claim"],
                    "expected_consequence": expected,
                    "observed_consequence": route.get(
                        "observed_consequence",
                        expected if value == expected_value else "DEVIATION",
                    ),
                    "failure_or_authorization_path": route[
                        "failure_or_authorization_path"
                    ],
                    "requested_claim_types": route["requested_claim"],
                    "deterministic_request_count": route.get("request_count", 1),
                    "route_ids": route.get("route_id", "fixture-route"),
                }
            )
        if cross_construct_routes:
            requested_claims = sorted(
                route["requested_claim"] for route in cross_construct_routes
            )
            rows.append(
                {
                    "dataset": name.upper().replace("_", "-"),
                    "evidence_condition": "cross-construct request",
                    "requested_claim": (
                        "multiple excluded typed claims; see artifact manifest"
                    ),
                    "expected_consequence": "REFUSE",
                    "observed_consequence": (
                        "REFUSE"
                        if all(
                            route["observed_consequence"] == "REFUSE"
                            for route in cross_construct_routes
                        )
                        else "DEVIATION"
                    ),
                    "failure_or_authorization_path": "construct mismatch",
                    "requested_claim_types": ", ".join(requested_claims),
                    "deterministic_request_count": sum(
                        route["request_count"] for route in cross_construct_routes
                    ),
                    "route_ids": ", ".join(
                        route["route_id"] for route in cross_construct_routes
                    ),
                }
            )
    return rows


def specification_surface_rows(surface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, result in surface["corpora"].items():
        summary = result["survival_summary"]
        consequences = result["certificate_consequences"]
        rows.append(
            {
                "corpus": name,
                "configurations": result["configuration_count"],
                "interactions": result["bounded_interaction_configuration_count"],
                "default_edges": result["baseline_edge_count"],
                "union_edges": result["union_edge_count"],
                "minimum_survival": summary["edge_minimum"],
                "mean_survival": summary["edge_mean"],
                "default_mean_survival": summary["default_edge_mean"],
                "intersection_edges": result["edge_set_geometry"][
                    "intersection_count"
                ],
                "emergent_edges": result["edge_set_geometry"]["emergent_count"],
                "one_to_one_component_overlap": summary["component_overlap_mean"],
                "admitted_union_edges": consequences["admitted_union_edges"],
                "qualified_union_edges": consequences["qualified_union_edges"],
                "admitted_default_edges": consequences["admitted_default_edges"],
                "qualified_default_edges": consequences["qualified_default_edges"],
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Cannot write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _latex_escape(value: object) -> str:
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "\\": r"\textbackslash{}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def _display_value(key: str, value: Any) -> str:
    if key == "corpus":
        return _corpus_label(str(value))
    if isinstance(value, float):
        if key == "rate" or key.endswith("_rate"):
            return f"{value:.3%}" if 0 < value < 0.001 else f"{value:.1%}"
        if key in {"wall_seconds", "peak_mib"}:
            return f"{value:.3f}"
        return f"{value:.3f}"
    return str(value)


def _write_latex_table(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str, str]],
    caption: str,
    label: str,
) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty table: {path}")
    alignment = "".join(column[2] for column in columns)
    header = " & ".join(_latex_escape(column[1]) for column in columns)
    body = [
        " & ".join(
            _latex_escape(_display_value(key, row[key])) for key, _, _ in columns
        )
        + r" \\"
        for row in rows
    ]
    font_size = r"\scriptsize" if any("p{" in column[2] for column in columns) else r"\small"
    lines = [
        r"\begin{table*}[t]",
        f"  \\caption{{{_latex_escape(caption)}}}",
        f"  \\label{{{label}}}",
        r"  \centering",
        f"  {font_size}",
        *([r"  \setlength{\tabcolsep}{1.2pt}"] if len(columns) >= 8 else []),
        f"  \\begin{{tabular}}{{{alignment}}}",
        r"    \toprule",
        f"    {header} " + r"\\",
        r"    \midrule",
        *(f"    {line}" for line in body),
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table*}",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="ascii")


def _write_policy_claim_table(
    table_root: Path,
    rows: list[dict[str, Any]],
    policy_version: str,
) -> None:
    typing_rows = [
        " & ".join(
            _latex_escape(_display_value(key, row[key]))
            for key in (
                "family",
                "claim",
                "object_signatures",
                "sufficient_predicate",
                "scope",
            )
        )
        + r" \\"
        for row in rows
    ]
    consequence_rows = [
        " & ".join(
            _latex_escape(_display_value(key, row[key]))
            for key in ("claim", "adjudication", "conflict", "encoding", "fallback")
        )
        + r" \\"
        for row in rows
    ]
    consequence_path = table_root / "policy_claim_consequences.tex"
    consequence_path.write_text(
        "\n".join(
            [
                r"  \textbf{(b) Representation consequences and lawful fallback projections}\par\smallskip",
                r"  \begin{tabular}{@{}p{.16\textwidth}p{.13\textwidth}p{.20\textwidth}p{.14\textwidth}p{.25\textwidth}@{}}",
                r"    \toprule",
                r"    Claim type & Adjudication & Counterevidence & Encoding & Fallback / projection \\",
                r"    \midrule",
                *(f"    {line}" for line in consequence_rows),
                r"    \bottomrule",
                r"  \end{tabular}",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    (table_root / "policy_claim_types.tex").write_text(
        "\n".join(
            [
                r"\begin{table*}[t]",
                f"  \\caption{{Instantiated Policy {policy_version} claim types and consequences used in this study.}}",
                r"  \label{tab:policy-claim-types}",
                r"  \centering",
                r"  \scriptsize",
                r"  \textbf{(a) Families, governed-object signatures, sufficient evidence predicates, and scope semantics}\par\smallskip",
                r"  \begin{tabular}{@{}p{.12\textwidth}p{.16\textwidth}p{.15\textwidth}p{.35\textwidth}p{.08\textwidth}@{}}",
                r"    \toprule",
                r"    Family & Claim type & Object signature & Sufficient bundle predicate & Scope \\",
                r"    \midrule",
                *(f"    {line}" for line in typing_rows),
                r"    \bottomrule",
                r"  \end{tabular}\par",
                r"  \medskip",
                r"  \input{../artifacts/tables/policy_claim_consequences.tex}",
                r"\end{table*}",
                "",
            ]
        ),
        encoding="ascii",
    )


def _write_manuscript_statistics(path: Path, surface: dict[str, Any]) -> None:
    corpora = surface["corpora"]
    acmart = corpora.get("acmart")
    if acmart is None and len(corpora) == 1:
        acmart = next(iter(corpora.values()))
    if acmart is None:
        raise KeyError("Specification surface has no acmart corpus")
    geometry = acmart["edge_set_geometry"]
    summary = acmart["survival_summary"]
    consequences = acmart["certificate_consequences"]
    values = {
        "TGAcmtUnionEdges": f"{acmart['union_edge_count']:,}",
        "TGAcmtAuthorizedEdges": f"{consequences['admitted_union_edges']:,}",
        "TGAcmtQualifiedEdges": f"{consequences['qualified_union_edges']:,}",
        "TGAcmtIntersectionEdges": f"{geometry['intersection_count']:,}",
        "TGAcmtDefaultMeanPersistence": f"{summary['default_edge_mean']:.3f}",
        "TGAcmtComponentJaccard": f"{summary['component_overlap_mean']:.3f}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in values.items()
        )
        + "\n",
        encoding="ascii",
    )


def _save_figure(fig: Any, output_stem: Path) -> list[Path]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    outputs = [
        output_stem.with_suffix(".pdf"),
        output_stem.with_suffix(".svg"),
        output_stem.with_suffix(".png"),
    ]
    fig.savefig(
        outputs[0],
        bbox_inches="tight",
        metadata={"Creator": "ThemeGraph publication pipeline", "CreationDate": None},
    )
    fig.savefig(
        outputs[1],
        bbox_inches="tight",
        metadata={"Creator": "ThemeGraph publication pipeline", "Date": None},
    )
    fig.savefig(outputs[2], bbox_inches="tight", dpi=600)
    return outputs


def _panel_title(axis: Any, label: str, title: str) -> None:
    axis.text(
        0.0,
        1.08,
        label,
        transform=axis.transAxes,
        color=PALETTE["vermilion"],
        fontsize=7,
        fontweight="bold",
        va="bottom",
    )
    axis.text(
        0.075,
        1.08,
        title,
        transform=axis.transAxes,
        color=PALETTE["ink"],
        fontsize=8.5,
        fontweight="bold",
        va="bottom",
    )


def _quiet_grid(axis: Any, direction: str = "x") -> None:
    axis.grid(axis=direction, color=PALETTE["line"], linewidth=0.55, alpha=0.8)
    axis.set_axisbelow(True)


def _job_ads_quality_figure(rows: list[dict[str, Any]], output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 2.25), constrained_layout=True)
    axis = fig.subplots()
    labels = [row["measure"] for row in rows]
    rates = [row["rate"] for row in rows]
    positions = list(range(len(rows)))
    colors = [PALETTE["blue"], PALETTE["gold"], PALETTE["vermilion"]]
    for position, rate, color in zip(positions, rates, colors, strict=True):
        axis.hlines(position, 0, rate, color=color, linewidth=2.2)
        axis.scatter(rate, position, s=48, color=color, edgecolor="white", linewidth=0.8, zorder=3)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlim(0, 0.82)
    axis.xaxis.set_major_formatter(PercentFormatter(1.0))
    axis.set_xlabel("Share of 18,870 workbook rows")
    _panel_title(axis, "A", "Observed data-quality conditions")
    _quiet_grid(axis)
    for position, row, rate in zip(positions, rows, rates, strict=True):
        rate_label = f"{rate:.3%}" if 0 < rate < 0.001 else f"{rate:.1%}"
        axis.text(
            min(rate + 0.018, 0.78),
            position,
            f"{rate_label}  |  {row['count']:,}",
            va="center",
            color=PALETTE["ink"],
            fontsize=7,
            fontweight="bold",
        )
    return _save_figure(fig, output_stem)


def _corpus_structure_figure(rows: list[dict[str, Any]], output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 3.15), constrained_layout=True)
    axes = fig.subplots(1, 3, gridspec_kw={"width_ratios": [1.35, 0.85, 0.95]})
    positions = list(range(len(rows)))
    labels = [_corpus_label(row["corpus"]) for row in rows]
    nodes = [row["nodes"] for row in rows]
    edges = [row["edges"] for row in rows]
    for position, node_count, edge_count in zip(positions, nodes, edges, strict=True):
        axes[0].plot([node_count, edge_count], [position, position], color=PALETTE["line"], linewidth=2.0)
    axes[0].scatter(nodes, positions, color=PALETTE["blue"], marker="o", s=28, zorder=3, label="Nodes")
    axes[0].scatter(edges, positions, color=PALETTE["gold"], marker="s", s=26, zorder=3, label="Edges")
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[0].set_xscale("log")
    axes[0].xaxis.set_major_locator(LogLocator(base=10, numticks=4))
    axes[0].xaxis.set_minor_formatter(NullFormatter())
    axes[0].set_xlabel("Count (log scale)")
    _panel_title(axes[0], "A", "Graph extent")
    axes[0].legend(loc="upper right", ncol=2, handletextpad=0.35, columnspacing=0.7)
    scc_values = [row["largest_scc"] for row in rows]
    for position, value in zip(positions, scc_values, strict=True):
        axes[1].hlines(position, 0, value, color=PALETTE["teal"], linewidth=1.8)
    axes[1].scatter(scc_values, positions, color=PALETTE["teal"], s=30, zorder=3)
    axes[1].set_yticks(positions, [])
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Nodes")
    _panel_title(axes[1], "B", "Largest SCC")
    asymmetry = [row["asymmetric_edge_rate"] for row in rows]
    for position, value in zip(positions, asymmetry, strict=True):
        axes[2].hlines(position, 0, value, color=PALETTE["vermilion"], linewidth=1.8)
    axes[2].scatter(asymmetry, positions, color=PALETTE["vermilion"], marker="D", s=28, zorder=3)
    axes[2].set_yticks(positions, [])
    axes[2].invert_yaxis()
    axes[2].set_xlim(0, 1)
    axes[2].xaxis.set_major_formatter(PercentFormatter(1.0))
    axes[2].set_xlabel("Retained edges")
    _panel_title(axes[2], "C", "Conditional asymmetry")
    for axis in axes:
        _quiet_grid(axis)
    return _save_figure(fig, output_stem)


def _threshold_sensitivity_figure(
    rows: list[dict[str, Any]], output_stem: Path
) -> list[Path]:
    corpus_names = [
        name
        for name in (
            "glassdoor_simplyhired_jobs",
            "glassdoor_simplyhired_jobs_unique_descriptions",
            "onet_500",
            "acmart",
            "python_stdlib_100",
        )
        if any(row["corpus"] == name for row in rows)
    ]
    if not corpus_names:
        return []
    confidence_values = sorted({row["min_confidence"] for row in rows})
    lift_values = sorted({row["min_lift"] for row in rows})
    maximum = max(row["largest_scc"] for row in rows if row["corpus"] in corpus_names)
    fig = Figure(figsize=(7.1, 2.35), constrained_layout=True)
    axes = fig.subplots(1, len(corpus_names), squeeze=False, sharex=True, sharey=True)
    image = None
    for axis, name in zip(axes.flat, corpus_names, strict=False):
        values = {
            (row["min_confidence"], row["min_lift"]): row["largest_scc"]
            for row in rows
            if row["corpus"] == name
        }
        matrix = [
            [values[(confidence, lift)] for lift in lift_values]
            for confidence in confidence_values
        ]
        image = axis.imshow(
            matrix,
            cmap="cividis",
            vmin=0,
            vmax=maximum,
            aspect="auto",
        )
        for row_index, row_values in enumerate(matrix):
            for column_index, value in enumerate(row_values):
                text_color = "white" if value > maximum * 0.55 else "black"
                axis.text(
                    column_index,
                    row_index,
                    str(value),
                    ha="center",
                    va="center",
                    color=text_color,
                    fontweight="bold",
                )
        axis.set_xticks(range(len(lift_values)), [str(value) for value in lift_values])
        axis.set_yticks(
            range(len(confidence_values)), [str(value) for value in confidence_values]
        )
        axis.set_xlabel("Lift")
        axis.set_title(_corpus_label(name), fontsize=7.5, pad=5, color=PALETTE["ink"])
    axes.flat[0].set_ylabel("Confidence")
    for axis in list(axes.flat)[len(corpus_names) :]:
        axis.set_visible(False)
    if image is not None:
        colorbar = fig.colorbar(image, ax=axes.ravel().tolist(), label="Largest SCC (nodes)", fraction=0.022, pad=0.02)
        colorbar.outline.set_linewidth(0.5)
    fig.suptitle("THRESHOLD RESPONSE  |  Largest strongly connected component", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=PALETTE["ink"])
    return _save_figure(fig, output_stem)


def _performance_figure(rows: list[dict[str, Any]], output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 2.8), constrained_layout=True)
    axes = fig.subplots(1, 2)
    colors = matplotlib.colormaps["cividis"].resampled(max(len(rows), 2)).colors
    handles = []
    for row, color in zip(rows, colors, strict=False):
        label = _corpus_label(row["corpus"])
        axes[0].scatter(row["units"], row["wall_seconds"], color=color, s=38, edgecolor="white", linewidth=0.7, zorder=3)
        axes[1].scatter(row["units"], row["peak_mib"], color=color, s=38, edgecolor="white", linewidth=0.7, zorder=3)
        handles.append(Line2D([], [], marker="o", linestyle="", markerfacecolor=color, markeredgecolor="white", label=label))
    for axis in axes:
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.xaxis.set_major_locator(LogLocator(base=10, numticks=5))
        axis.xaxis.set_minor_formatter(NullFormatter())
        axis.yaxis.set_minor_formatter(NullFormatter())
        axis.set_xlabel("Extracted text units (log scale)")
        axis.grid(color=PALETTE["line"], linewidth=0.5, alpha=0.8)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Core wall time, seconds")
    _panel_title(axes[0], "A", "Observed execution time")
    axes[1].set_ylabel("Peak traced Python allocation, MiB")
    _panel_title(axes[1], "B", "Observed allocation")
    fig.legend(handles=handles, loc="outside lower center", ncol=3, handletextpad=0.35, columnspacing=0.9)
    return _save_figure(fig, output_stem)


def _edge_distribution_figure(
    rows: list[dict[str, Any]], output_stem: Path
) -> list[Path]:
    fig = Figure(figsize=(7.1, 3.05), constrained_layout=True)
    axes = fig.subplots(1, 3)
    labels = [_corpus_label(row["corpus"]) for row in rows]
    positions = list(range(len(rows)))
    metrics = [
        ("confidence", "Conditional confidence"),
        ("support", "Supporting units"),
        ("lift", "Lift"),
    ]
    for panel, (axis, (key, title)) in enumerate(zip(axes, metrics, strict=True)):
        for position, row in zip(positions, rows, strict=True):
            low = row[f"{key}_p25"]
            middle = row[f"{key}_median"]
            high = row[f"{key}_p75"]
            axis.hlines(position, low, high, color=PALETTE["blue"], linewidth=2.2)
            axis.plot(middle, position, "o", color=PALETTE["vermilion"], markersize=4.5, markeredgecolor="white", markeredgewidth=0.6)
        axis.set_yticks(positions, labels if axis is axes[0] else [])
        axis.invert_yaxis()
        _panel_title(axis, chr(ord("A") + panel), title)
        axis.set_xlabel("Median  |  interquartile range")
        _quiet_grid(axis)
    axes[1].set_xscale("log")
    return _save_figure(fig, output_stem)


def _claim_benchmark_figure(
    benchmark: dict[str, Any], output_stem: Path
) -> list[Path]:
    cases = benchmark["claim_decisions"]["cases"]
    fig = Figure(figsize=(7.1, 3.65))
    axis = fig.subplots()
    fig.subplots_adjust(left=0.22, right=0.98, bottom=0.18, top=0.88)
    decision_colors = {
        "ADMIT": PALETTE["teal"],
        "QUALIFY": PALETTE["gold"],
        "REFUSE": PALETTE["vermilion"],
    }
    positions = list(range(len(cases)))
    decisions = [case["certificate"]["decision"] for case in cases]
    decision_x = {"REFUSE": 0, "QUALIFY": 1, "ADMIT": 2}
    axis.axvspan(-0.35, 0.35, color=PALETTE["red_pale"], zorder=0)
    axis.axvspan(0.65, 1.35, color=PALETTE["gold_pale"], zorder=0)
    axis.axvspan(1.65, 2.35, color=PALETTE["teal_pale"], zorder=0)
    for position, decision in zip(positions, decisions, strict=True):
        axis.scatter(
            decision_x[decision],
            position,
            s=52,
            color=decision_colors[decision],
            marker={"REFUSE": "X", "QUALIFY": "D", "ADMIT": "o"}[decision],
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
    axis.set_yticks(
        positions,
        [case["case_id"].replace("-", " ") for case in cases],
    )
    axis.invert_yaxis()
    axis.set_xlim(-0.5, 3.95)
    axis.set_xticks([0, 1, 2], ["REFUSE", "QUALIFY", "ADMIT"])
    axis.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False)
    axis.spines["bottom"].set_visible(False)
    _panel_title(axis, "A", "Ten controlled claim decisions")
    for position, case, decision in zip(positions, cases, decisions, strict=True):
        certificate = case["certificate"]
        fallback = certificate["fallback_claim"]
        axis.text(
            2.55,
            position,
            (
                f"fallback  {fallback.replace('-', ' ')}"
                if fallback
                else f"encoding  {certificate['allowed_encoding'].replace('-', ' ')}"
            ),
            va="center",
            color=PALETTE["slate"],
            fontsize=6.8,
        )
    axis.text(2.55, -0.8, "REPRESENTATION CONSEQUENCE", color=PALETTE["gray"], fontsize=6.5, fontweight="bold")
    metrics = benchmark["claim_decisions"]
    axis.text(
        0.0,
        -0.12,
        (
            f"Policy conformance {metrics['policy_conformance_rate']:.0%}; "
            f"decision disagreement {metrics['decision_disagreement_rate']:.0%}; "
            f"fallback disagreement {metrics['fallback_disagreement_rate']:.0%}."
        ),
        transform=axis.transAxes,
        fontsize=6.8,
        color=PALETTE["slate"],
    )
    axis.grid(axis="y", color=PALETTE["line"], linewidth=0.45)
    axis.set_axisbelow(True)
    return _save_figure(fig, output_stem)


def _evidence_transition_figure(
    benchmark: dict[str, Any], output_stem: Path
) -> list[Path]:
    transition = benchmark["directed_reference_transition"]
    fig = Figure(figsize=(7.1, 2.45), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    axis.add_patch(Rectangle((0.015, 0.12), 0.46, 0.76, facecolor="#FAFBFC", edgecolor=PALETTE["line"], linewidth=0.7, transform=axis.transAxes))
    axis.add_patch(Rectangle((0.525, 0.12), 0.46, 0.76, facecolor="#FAFBFC", edgecolor=PALETTE["line"], linewidth=0.7, transform=axis.transAxes))
    axis.text(0.035, 0.82, "A  IDENTIFICATION FAILS", transform=axis.transAxes, fontsize=6.8, fontweight="bold", color=PALETTE["vermilion"])
    axis.text(0.545, 0.82, "B  CONSTRUCT-MATCHED CHANNEL", transform=axis.transAxes, fontsize=6.8, fontweight="bold", color=PALETTE["teal"])
    _add_module(axis, (0.04, 0.47), 0.13, 0.22, "Co-occurrence", "OBSERVED", PALETTE["blue_pale"], PALETTE["blue"])
    _add_module(axis, (0.20, 0.47), 0.11, 0.22, "Prerequisite", "REQUEST", PALETTE["gold_pale"], PALETTE["gold"])
    _add_module(axis, (0.34, 0.47), 0.11, 0.22, "REFUSE", f"POLICY {POLICY_VERSION}", PALETTE["red_pale"], PALETTE["vermilion"])
    _add_arrow(axis, (0.17, 0.58), (0.20, 0.58))
    _add_arrow(axis, (0.31, 0.58), (0.34, 0.58), PALETTE["vermilion"])
    axis.text(0.245, 0.27, "policy-preferred lexical fallback", ha="center", transform=axis.transAxes, fontsize=6.8, color=PALETTE["slate"])
    _add_module(axis, (0.55, 0.47), 0.14, 0.22, "Co-occurrence\n+ prerequisite ref.", "OBSERVED", PALETTE["blue_pale"], PALETTE["blue"])
    _add_module(axis, (0.72, 0.47), 0.10, 0.22, "Prerequisite", "REQUEST", PALETTE["gold_pale"], PALETTE["gold"])
    _add_module(axis, (0.85, 0.47), 0.11, 0.22, "ADMIT", f"POLICY {POLICY_VERSION}", PALETTE["teal_pale"], PALETTE["teal"])
    _add_arrow(axis, (0.69, 0.58), (0.72, 0.58))
    _add_arrow(axis, (0.82, 0.58), (0.85, 0.58), PALETTE["teal"])
    axis.text(0.755, 0.27, "directed reference encoding", ha="center", transform=axis.transAxes, fontsize=6.8, color=PALETTE["slate"])
    axis.text(0.5, 0.18, "Matched evidence changes the permissible representation", ha="center", va="center", transform=axis.transAxes, fontsize=6.2, color=PALETTE["slate"])
    axis.text(
        0.5,
        0.02,
        (
            f"All {len(transition['reference_edges'])} controlled requests transition "
            "from REFUSE to ADMIT after exactly matched prerequisite evidence."
        ),
        ha="center",
        transform=axis.transAxes,
        fontsize=6.5,
        color=PALETTE["slate"],
    )
    return _save_figure(fig, output_stem)


def _specification_survival_figure(
    surface: dict[str, Any], output_stem: Path
) -> list[Path]:
    corpora = list(surface["corpora"].items())
    fig = Figure(figsize=(7.1, 3.0))
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.16, right=0.98, bottom=0.2, top=0.88, wspace=0.28)
    colors = [
        PALETTE["blue"],
        PALETTE["green"],
        PALETTE["orange"],
        PALETTE["red"],
    ]
    for position, ((name, result), color) in enumerate(
        zip(corpora, colors, strict=False)
    ):
        values = sorted(result["edge_survival"].values())
        summary = result["survival_summary"]
        minimum = summary["edge_minimum"]
        maximum = max(values) if values else 0.0
        lower_quartile = summary.get("edge_p25", _percentile(values, 0.25))
        upper_quartile = summary.get("edge_p75", _percentile(values, 0.75))
        median_survival = summary.get("edge_median", median(values) if values else 0.0)
        axes[0].hlines(position, minimum, maximum, color=PALETTE["line"], linewidth=1.2)
        axes[0].hlines(position, lower_quartile, upper_quartile, color=color, linewidth=6.0)
        axes[0].scatter(median_survival, position, color="white", edgecolor=color, linewidth=1.1, s=26, zorder=3)
        axes[0].scatter(summary["edge_mean"], position, color=PALETTE["ink"], marker="D", s=20, zorder=4)
        frontier = result["gate_frontier"]
        gate_values = [row["survival_gate"] for row in frontier]
        admission_values = [
                row["admitted_union_edges"] / result["union_edge_count"]
                if result["union_edge_count"]
                else 0.0
                for row in frontier
            ]
        axes[1].step(
            gate_values,
            admission_values,
            where="post",
            linewidth=1.2,
            color=color,
            label=_corpus_label(name),
        )
        axes[1].scatter(
            gate_values,
            admission_values,
            marker={0: "o", 1: "s", 2: "^", 3: "D"}.get(position, "o"),
            s=23,
            color=color,
            edgecolor="white",
            linewidth=0.5,
            zorder=4,
        )
    axes[0].axvspan(0.79, 0.81, color=PALETTE["red_pale"], zorder=0)
    axes[0].axvline(0.8, color=PALETTE["vermilion"], linestyle="--", linewidth=1.0)
    axes[0].set_yticks(
        range(len(corpora)),
        [_corpus_label(name) for name, _ in corpora],
    )
    configuration_counts = sorted(
        {result["configuration_count"] for _, result in corpora}
    )
    count_label = "/".join(str(value) for value in configuration_counts)
    axes[0].set_xlim(-0.02, 1.02)
    axes[0].set_xlabel(f"Union-edge persistence across {count_label} configurations")
    _panel_title(axes[0], "A", "Distribution of edge persistence")
    _quiet_grid(axes[0])
    axes[0].text(
        0.79,
        0.94,
        "persistence gate",
        transform=axes[0].get_xaxis_transform(),
        color=PALETTE["vermilion"],
        fontsize=6.5,
        ha="right",
        va="top",
        rotation=90,
    )
    axes[1].axvspan(0.79, 0.81, color=PALETTE["red_pale"], zorder=0)
    axes[1].axvline(0.8, color=PALETTE["vermilion"], linestyle="--", linewidth=1.0)
    axes[1].set_xlim(0.48, 1.02)
    axes[1].set_ylim(-0.02, 1.02)
    axes[1].set_xlabel("Candidate persistence gate")
    axes[1].set_ylabel("Share of union edges passing persistence gate")
    _panel_title(axes[1], "B", "Persistence-gate frontier")
    axes[1].grid(color=PALETTE["line"], linewidth=0.5, alpha=0.8)
    axes[1].set_axisbelow(True)
    axes[1].legend(fontsize=6.3, loc="upper right", handlelength=1.7, labelspacing=0.3)
    return _save_figure(fig, output_stem)


def _external_validation_figure(
    validation: dict[str, Any], output_stem: Path
) -> list[Path]:
    fig = Figure(figsize=(7.1, 5.35))
    axes = fig.subplots(1, 2, gridspec_kw={"width_ratios": (1.25, 1.05)})
    fig.subplots_adjust(left=0.12, right=0.98, bottom=0.19, top=0.92, wspace=0.20)
    datasets = validation["datasets"]
    mrpc = datasets["mrpc"]["label_counts"]
    paws = datasets["paws"]["label_counts"]
    snli = datasets["snli"]["label_counts"]
    al_cpl = datasets["al_cpl"]["label_counts"]
    torque_relations = datasets["torque"]["record_count"]
    conditions = [
        ("MRPC equivalence +", mrpc["paraphrase"], "authorized", PALETTE["blue"]),
        ("MRPC non-equivalence", mrpc["non_paraphrase"], "counterevidence", PALETTE["blue"]),
        ("MRPC cross-construct", datasets["mrpc"]["record_count"], "construct mismatch", PALETTE["blue"]),
        ("PAWS equivalence +", paws["paraphrase"], "authorized", PALETTE["gold"]),
        ("PAWS non-equivalence", paws["non_paraphrase"], "counterevidence", PALETTE["gold"]),
        ("PAWS cross-construct", datasets["paws"]["record_count"], "construct mismatch", PALETTE["gold"]),
        ("SNLI entailment +", snli["entailment"], "authorized", PALETTE["teal"]),
        ("SNLI neutral", snli["neutral"], "insufficient", PALETTE["slate"]),
        ("SNLI contradiction", snli["contradiction"], "counterevidence", PALETTE["vermilion"]),
        ("SNLI reversed request", snli["entailment"], "scope mismatch", PALETTE["teal"]),
        ("AL-CPL prerequisite +", al_cpl["prerequisite"], "authorized", PALETTE["green"]),
        ("AL-CPL mention only", al_cpl["prerequisite"], "channel absent", PALETTE["slate"]),
        ("AL-CPL negative", al_cpl["non_prerequisite"], "counterevidence", PALETTE["green"]),
        ("AL-CPL reversed request", al_cpl["prerequisite"], "scope mismatch", PALETTE["green"]),
        ("TORQUE event order +", torque_relations, "authorized", PALETTE["orange"]),
        ("TORQUE mention only", torque_relations, "mention-order insufficient", PALETTE["slate"]),
        ("TORQUE reversed request", torque_relations, "scope mismatch", PALETTE["orange"]),
    ]
    positions = list(range(len(conditions)))
    route_families = (
        ("Matched\nsupport", lambda text: text.startswith("matched")),
        ("Counter-\nevidence", lambda text: "negative" in text or "contradiction" in text),
        ("Reversal", lambda text: text == "reversed relation request"),
        ("Mention\nonly", lambda text: text == "mention order only"),
        ("Cross-\nconstruct", lambda text: text == "cross-construct request"),
    )
    dataset_order = ("mrpc", "paws", "snli", "al_cpl", "torque")
    coverage = [
        [
            sum(
                predicate(route["evidence_condition"])
                for route in datasets[dataset]["contract_routes"]
            )
            for _, predicate in route_families
        ]
        for dataset in dataset_order
    ]
    applicable = {
        "mrpc": (True, True, False, False, True),
        "paws": (True, True, False, False, True),
        "snli": (True, True, True, False, True),
        "al_cpl": (True, True, True, True, True),
        "torque": (True, False, True, True, True),
    }
    axes[0].set_xlim(-0.5, len(route_families) - 0.5)
    axes[0].set_ylim(len(dataset_order) - 0.5, -0.5)
    for row_index, row in enumerate(coverage):
        for column_index, count in enumerate(row):
            is_applicable = applicable[dataset_order[row_index]][column_index]
            axes[0].add_patch(
                Rectangle(
                    (column_index - 0.43, row_index - 0.38),
                    0.86,
                    0.76,
                    facecolor="white" if is_applicable else PALETTE["mist"],
                    edgecolor=PALETTE["teal"] if count else PALETTE["line"],
                    linewidth=1.4 if count else 0.8,
                )
            )
            axes[0].text(
                column_index,
                row_index,
                f"\N{CHECK MARK} {count}"
                if count
                else ("0" if is_applicable else "N/A"),
                ha="center",
                va="center",
                color=PALETTE["ink"] if is_applicable else PALETTE["slate"],
                fontsize=6.5,
                fontweight="bold",
            )
    axes[0].set_yticks(range(len(dataset_order)), [name.upper().replace("_", "-") for name in dataset_order])
    axes[0].set_xticks(range(len(route_families)), [label for label, _ in route_families])
    axes[0].set_xlabel("Categorical route coverage (check = exercised; N/A = inapplicable)")
    _panel_title(axes[0], "A", "Construct-boundary route coverage")
    gate_order = (
        "authorized",
        "channel absent",
        "insufficient",
        "counterevidence",
        "scope mismatch",
        "mention-order insufficient",
        "construct mismatch",
    )
    gate_positions = {gate: index for index, gate in enumerate(gate_order)}
    for position, (_, _, gate, color) in zip(positions, conditions, strict=True):
        marker = "o" if gate == "authorized" else "X"
        axes[1].scatter(
            gate_positions[gate], position, color=color, s=42,
            marker=marker, edgecolor="white", linewidth=0.8, zorder=3
        )
    dataset_groups = (
        (1.0, "MRPC"),
        (4.0, "PAWS"),
        (8.0, "SNLI"),
        (12.0, "AL-CPL"),
        (15.0, "TORQUE"),
    )
    axes[1].set_yticks(
        [position for position, _ in dataset_groups],
        [label for _, label in dataset_groups],
    )
    axes[1].tick_params(axis="y", length=0, labelsize=5.8, pad=2)
    for boundary in (2.5, 5.5, 9.5, 13.5):
        axes[1].axhline(boundary, color=PALETTE["line"], linewidth=0.6, zorder=0)
    axes[1].invert_yaxis()
    axes[1].set_xlim(-0.4, len(gate_order) - 0.6)
    gate_labels = {
        "authorized": "AUTH",
        "channel absent": "ABS",
        "insufficient": "INS",
        "counterevidence": "CTR",
        "scope mismatch": "SCP",
        "mention-order insufficient": "M-ORD",
        "construct mismatch": "X-CON",
    }
    axes[1].set_xticks(
        range(len(gate_order)),
        [gate_labels[gate] for gate in gate_order],
        rotation=0,
        ha="center",
    )
    axes[1].tick_params(axis="x", labelsize=5.3, pad=2)
    axes[1].set_xlabel("Policy path")
    _panel_title(axes[1], "B", "Deterministic authorization paths")
    _quiet_grid(axes[1])
    fig.text(
        0.61,
        0.075,
        "AUTH authorized  |  ABS evidence channel absent  |  INS insufficient  |  CTR counterevidence\n"
        "SCP scope mismatch  |  M-ORD mention-order insufficient  |  X-CON construct mismatch",
        ha="center",
        va="center",
        fontsize=5.35,
        color=PALETTE["slate"],
        linespacing=1.45,
    )
    return _save_figure(fig, output_stem)


def _add_box(axis: Any, position: tuple[float, float], text: str, color: str) -> None:
    x_value, y_value = position
    _add_module(axis, (x_value, y_value), 0.16, 0.20, text, "", color, PALETTE["slate"])


def _add_module(
    axis: Any,
    position: tuple[float, float],
    width: float,
    height: float,
    text: str,
    kicker: str,
    facecolor: str,
    accent: str,
    body_fontsize: float = 6.7,
) -> None:
    x_value, y_value = position
    axis.add_patch(
        Rectangle(
            (x_value, y_value),
            width,
            height,
            facecolor=facecolor,
            edgecolor=PALETTE["line"],
            linewidth=0.7,
            transform=axis.transAxes,
        )
    )
    axis.add_patch(Rectangle((x_value, y_value), 0.007, height, facecolor=accent, edgecolor="none", transform=axis.transAxes))
    if kicker:
        axis.text(x_value + 0.018, y_value + height - 0.035, kicker, transform=axis.transAxes, fontsize=5.3, fontweight="bold", color=accent, va="top")
    axis.text(x_value + width / 2 + 0.004, y_value + height * (0.46 if kicker else 0.5), text, ha="center", va="center", transform=axis.transAxes, fontsize=body_fontsize, color=PALETTE["ink"], fontweight="bold")


def _add_arrow(
    axis: Any, start: tuple[float, float], end: tuple[float, float], color: str = "black"
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=0.9,
            color=PALETTE["slate"] if color == "black" else color,
            transform=axis.transAxes,
        )
    )


def _claim_admissibility_mapping(output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 2.75), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    _add_module(axis, (0.025, 0.38), 0.17, 0.25, "Unordered\ntext units", "OBSERVATION", PALETTE["blue_pale"], PALETTE["blue"])
    _add_module(axis, (0.24, 0.38), 0.18, 0.25, "support  |  confidence\nlift", "DERIVED STATISTICS", PALETTE["gold_pale"], PALETTE["gold"])
    _add_arrow(axis, (0.195, 0.505), (0.24, 0.505))
    axis.axvline(0.51, 0.08, 0.92, color=PALETTE["slate"], linewidth=0.8, linestyle=(0, (3, 3)))
    axis.text(0.51, 0.95, "CLAIM BOUNDARY", transform=axis.transAxes, ha="center", fontsize=6, fontweight="bold", color=PALETTE["slate"])
    lanes = [
        (0.69, "Lexical association", "ADMIT", PALETTE["teal_pale"], PALETTE["teal"]),
        (0.41, "Asymmetric conditional", "QUALIFY", PALETTE["gold_pale"], PALETTE["gold"]),
        (0.13, "Semantic direction", "REFUSE", PALETTE["red_pale"], PALETTE["vermilion"]),
    ]
    for y_value, claim, decision, facecolor, accent in lanes:
        _add_module(axis, (0.59, y_value), 0.22, 0.17, claim, "REQUESTED CLAIM", facecolor, accent)
        axis.add_patch(Rectangle((0.84, y_value), 0.13, 0.17, facecolor=accent, edgecolor="none", transform=axis.transAxes))
        axis.text(0.905, y_value + 0.085, decision, ha="center", va="center", transform=axis.transAxes, fontsize=6.8, color="white", fontweight="bold")
        connection_color = PALETTE["vermilion"] if decision == "REFUSE" else PALETTE["slate"]
        axis.plot([0.42, 0.54, 0.59], [0.505, y_value + 0.085, y_value + 0.085], transform=axis.transAxes, color=connection_color, linewidth=0.9, linestyle=(0, (3, 2)) if decision == "REFUSE" else "-")
    axis.scatter([0.51], [0.215], transform=axis.transAxes, s=42, marker="X", color=PALETTE["vermilion"], edgecolor="white", linewidth=0.7, zorder=4)
    axis.text(0.53, 0.065, "No construct-matched directional channel crosses the boundary", transform=axis.transAxes, fontsize=6.3, color=PALETTE["vermilion"], fontweight="bold")
    return _save_figure(fig, output_stem)


def _pipeline_mapping(output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 2.85), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    axis.text(0.02, 0.94, "REPRODUCIBLE EVIDENCE LINEAGE", transform=axis.transAxes, fontsize=8.5, fontweight="bold", color=PALETTE["ink"])
    axis.text(0.02, 0.875, "Every visual claim remains connected to source, transformation, aggregate result, and deterministic hash.", transform=axis.transAxes, fontsize=6.5, color=PALETTE["slate"])
    axis.add_patch(Rectangle((0.02, 0.56), 0.105, 0.22, facecolor=PALETTE["ink"], edgecolor="none", transform=axis.transAxes))
    axis.text(0.0725, 0.67, "ANALYSIS", transform=axis.transAxes, ha="center", va="center", fontsize=6.3, color="white", fontweight="bold")
    analysis = [
        (0.15, "Source + license", "INGEST", PALETTE["blue"]),
        (0.32, "Dataset adapter", "NORMALIZE", PALETTE["blue"]),
        (0.49, "Units + terms", "UNITIZE", PALETTE["gold"]),
        (0.66, "Association", "EXTRACT", PALETTE["gold"]),
        (0.83, "Graph + SCC", "ANALYZE", PALETTE["gold"]),
    ]
    for x_value, text, kicker, accent in analysis:
        facecolor = PALETTE["blue_pale"] if accent == PALETTE["blue"] else PALETTE["gold_pale"]
        _add_module(axis, (x_value, 0.56), 0.14, 0.22, text, kicker, facecolor, accent)
    for left, right in pairwise(analysis):
        _add_arrow(axis, (left[0] + 0.14, 0.67), (right[0], 0.67))
    axis.add_patch(Rectangle((0.02, 0.17), 0.105, 0.22, facecolor=PALETTE["ink"], edgecolor="none", transform=axis.transAxes))
    axis.text(0.0725, 0.28, "PUBLISH", transform=axis.transAxes, ha="center", va="center", fontsize=6.3, color="white", fontweight="bold")
    publication = [
        (0.15, "ACM manuscript", "RENDER", PALETTE["teal"]),
        (0.32, "Artifact manifest", "HASH", PALETTE["teal"]),
        (0.49, "Figures + tables", "GENERATE", PALETTE["teal"]),
        (0.66, "Validated JSON", "AGGREGATE", PALETTE["teal"]),
        (0.83, "Policy decisions", "CERTIFY", PALETTE["vermilion"]),
    ]
    for x_value, text, kicker, accent in publication:
        facecolor = PALETTE["red_pale"] if accent == PALETTE["vermilion"] else PALETTE["teal_pale"]
        _add_module(axis, (x_value, 0.17), 0.14, 0.22, text, kicker, facecolor, accent)
    for left, right in zip(publication[:0:-1], publication[-2::-1], strict=True):
        _add_arrow(axis, (left[0], 0.28), (right[0] + 0.14, 0.28))
    axis.plot([0.90, 0.90], [0.39, 0.56], transform=axis.transAxes, color=PALETTE["vermilion"], linewidth=1.0)
    axis.text(0.90, 0.475, "CLAIM-TIME CONTRACT", transform=axis.transAxes, fontsize=5.2, color=PALETTE["vermilion"], ha="center", va="center", fontweight="bold")
    axis.plot([0.15, 0.97], [0.105, 0.105], transform=axis.transAxes, color=PALETTE["line"], linewidth=0.7)
    axis.text(0.56, 0.04, "SHA-256 provenance spine  |  aggregate-only external evidence  |  deterministic rebuild", transform=axis.transAxes, ha="center", fontsize=6.2, color=PALETTE["slate"])
    return _save_figure(fig, output_stem)


def _themegraph_overview_architecture(output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 3.85), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    axis.text(0.02, 0.965, "THEMEGRAPH  |  EVIDENCE-CONSTRAINED REPRESENTATION GOVERNANCE", transform=axis.transAxes, fontsize=8.5, fontweight="bold", color=PALETTE["ink"])
    axis.text(0.02, 0.915, "Every semantic statement, mark, and requested-claim export crosses one certificate-required boundary.", transform=axis.transAxes, fontsize=6.4, color=PALETTE["slate"])

    axis.add_patch(Rectangle((0.02, 0.59), 0.575, 0.25, facecolor="#F8FAFB", edgecolor=PALETTE["line"], linewidth=0.7, transform=axis.transAxes))
    axis.text(0.035, 0.805, "COMPUTATION RAIL", transform=axis.transAxes, fontsize=5.7, fontweight="bold", color=PALETTE["blue"])
    computation = [
        (0.035, "Corpus +\nlineage", "OBSERVE", PALETTE["blue_pale"], PALETTE["blue"]),
        (0.175, "Units +\nterms", "EXTRACT", PALETTE["blue_pale"], PALETTE["blue"]),
        (0.315, "Association\nstatistics", "COMPUTE", PALETTE["gold_pale"], PALETTE["gold"]),
        (0.455, "Graph + SCCs\nstructural only", "ANALYZE", PALETTE["gold_pale"], PALETTE["gold"]),
    ]
    for x_value, text, kicker, facecolor, accent in computation:
        _add_module(axis, (x_value, 0.625), 0.12, 0.145, text, kicker, facecolor, accent, body_fontsize=5.7)
    for left, right in pairwise(computation):
        _add_arrow(axis, (left[0] + 0.12, 0.6975), (right[0], 0.6975))

    _add_module(axis, (0.035, 0.325), 0.18, 0.155, "Requested semantic\nrelation", "CLAIM RAIL", PALETTE["red_pale"], PALETTE["vermilion"], body_fontsize=5.9)
    _add_module(axis, (0.265, 0.325), 0.22, 0.155, "Observed channels + lineage\ncounterevidence + sensitivity", "TYPED EVIDENCE BUNDLE", PALETTE["teal_pale"], PALETTE["teal"], body_fontsize=5.15)
    _add_arrow(axis, (0.215, 0.4025), (0.265, 0.4025))
    _add_arrow(axis, (0.515, 0.625), (0.44, 0.48), PALETTE["gold"])

    axis.add_patch(Rectangle((0.545, 0.285), 0.19, 0.305, facecolor=PALETTE["ink"], edgecolor="none", transform=axis.transAxes))
    axis.text(0.64, 0.552, "REPRESENTATION MONITOR", ha="center", transform=axis.transAxes, fontsize=5.5, fontweight="bold", color="white")
    axis.text(0.64, 0.527, "CERTIFICATE REQUIRED", ha="center", transform=axis.transAxes, fontsize=4.25, fontweight="bold", color="#B9C5CF")
    gate_rows = [
        ("01", "Identifiability", PALETTE["vermilion"]),
        ("02", "Provenance", PALETTE["blue"]),
        ("03", "Sensitivity / uncertainty\n/ dependence", PALETTE["gold"]),
        ("04", "Conflict + policy-specific\ncaveats", PALETTE["teal"]),
    ]
    for index, (number, label, color) in enumerate(gate_rows):
        y_value = 0.492 - index * 0.055
        axis.text(0.565, y_value, number, transform=axis.transAxes, fontsize=5.2, fontweight="bold", color=color, va="center")
        axis.text(
            0.598,
            y_value,
            label,
            transform=axis.transAxes,
            fontsize=4.35,
            linespacing=0.9,
            color="white",
            va="center",
        )
    axis.text(0.64, 0.294, "identifiability first", ha="center", transform=axis.transAxes, fontsize=3.9, fontweight="bold", color="#B9C5CF")
    _add_arrow(axis, (0.485, 0.4025), (0.545, 0.4025))

    axis.add_patch(FancyArrowPatch((0.515, 0.77), (0.805, 0.77), arrowstyle="-|>", connectionstyle="arc3,rad=-0.22", mutation_scale=9, linewidth=0.8, linestyle=(0, (3, 2)), color=PALETTE["vermilion"], transform=axis.transAxes))
    axis.scatter([0.65], [0.817], transform=axis.transAxes, marker="X", s=38, color=PALETTE["vermilion"], edgecolor="white", linewidth=0.7, zorder=5)
    axis.text(0.65, 0.865, "CERTIFICATE-GUARDED BOUNDARY", ha="center", transform=axis.transAxes, fontsize=5.4, fontweight="bold", color=PALETTE["vermilion"])
    axis.text(0.65, 0.842, "8 certificate-guarded output entry points", ha="center", transform=axis.transAxes, fontsize=4.4, color=PALETTE["slate"])

    axis.text(0.77, 0.835, "GOVERNED REPRESENTATION", transform=axis.transAxes, fontsize=5.7, fontweight="bold", color=PALETTE["slate"])
    outcomes = [
        (0.665, "ADMIT", "matched semantics\npermitted", PALETTE["teal"], PALETTE["teal_pale"]),
        (0.485, "QUALIFY", "scoped mark +\nvisible caveat", PALETTE["gold"], PALETTE["gold_pale"]),
        (0.305, "REFUSE", "undirected\nfallback or\nblocked relation", PALETTE["vermilion"], PALETTE["red_pale"]),
    ]
    for y_value, decision, consequence, accent, facecolor in outcomes:
        _add_arrow(axis, (0.735, 0.4375), (0.775, y_value + 0.06), accent)
        axis.add_patch(Rectangle((0.775, y_value), 0.2, 0.12, facecolor=facecolor, edgecolor=PALETTE["line"], linewidth=0.7, transform=axis.transAxes))
        axis.add_patch(Rectangle((0.775, y_value), 0.052, 0.12, facecolor=accent, edgecolor="none", transform=axis.transAxes))
        axis.text(0.801, y_value + 0.06, decision, ha="center", va="center", rotation=90, transform=axis.transAxes, fontsize=5.2, color="white", fontweight="bold")
        axis.text(0.901, y_value + 0.06, consequence, ha="center", va="center", transform=axis.transAxes, fontsize=5.15, color=PALETTE["ink"], fontweight="bold")
    axis.text(0.875, 0.255, "Every output consumes the certificate:\nmark, statement, export, witness + remediation", ha="center", va="top", transform=axis.transAxes, fontsize=4.8, color=PALETTE["slate"], bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2}, zorder=6)

    axis.add_patch(Rectangle((0.02, 0.055), 0.955, 0.125, facecolor=PALETTE["mist"], edgecolor="none", transform=axis.transAxes))
    axis.text(0.04, 0.143, "ASSURANCE RAIL", transform=axis.transAxes, fontsize=5.5, fontweight="bold", color=PALETTE["ink"])
    assurance = [
        (0.19, "Conformance + mediation", "policy linting + eight guarded entry points"),
        (0.43, "External stress tests", "construct-matched evidence"),
        (0.71, "Specification surface", "sensitivity + gate frontier"),
    ]
    for x_value, title, subtitle in assurance:
        axis.scatter([x_value - 0.018], [0.115], transform=axis.transAxes, s=20, color=PALETTE["blue"], zorder=3)
        axis.text(x_value, 0.132, title, transform=axis.transAxes, fontsize=5.8, fontweight="bold", color=PALETTE["ink"], va="center")
        axis.text(x_value, 0.09, subtitle, transform=axis.transAxes, fontsize=5.2, color=PALETTE["slate"], va="center")
    axis.text(0.915, 0.115, "No human-benefit\nclaim", ha="center", va="center", transform=axis.transAxes, fontsize=5.0, fontweight="bold", color=PALETTE["vermilion"])
    axis.add_patch(FancyArrowPatch((0.89, 0.305), (0.125, 0.325), arrowstyle="-|>", connectionstyle="arc3,rad=-0.18", mutation_scale=8, linewidth=0.75, linestyle=(0, (3, 2)), color=PALETTE["slate"], transform=axis.transAxes))
    axis.text(0.5, 0.205, "witness + remediation return to the claim or evidence, never around the gate", ha="center", transform=axis.transAxes, fontsize=5.4, fontweight="bold", color=PALETTE["slate"], bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5}, zorder=5)
    return _save_figure(fig, output_stem)


def _epistemic_dependency_ladder(output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 2.75), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    stages = [
        ("Computational\ncorrectness", "tests implementation", "MECHANISM GATE", PALETTE["blue_pale"], PALETTE["blue"]),
        ("Construct /\nevidence match", "checks typed match", "CONSTRUCT GATE", PALETTE["teal_pale"], PALETTE["teal"]),
        ("Specification\npersistence", "tests sensitivity", "ROBUSTNESS GATE", PALETTE["gold_pale"], PALETTE["gold"]),
        ("Interpretive\nvalidity", "requires adjudication", "INTERPRETIVE GATE", PALETTE["red_pale"], PALETTE["vermilion"]),
        ("Human\nbenefit", "needs consequence evidence", "OUTCOME GATE", PALETTE["mist"], PALETTE["slate"]),
    ]
    axis.text(0.02, 0.94, "EPISTEMIC DEPENDENCY GATES", transform=axis.transAxes, fontsize=8.5, fontweight="bold", color=PALETTE["ink"])
    axis.text(0.02, 0.875, "Each gate asks a distinct design-specific evidentiary question; no gate logically entails the next.", transform=axis.transAxes, fontsize=6.5, color=PALETTE["slate"])
    for index, (title, subtitle, gate, facecolor, accent) in enumerate(stages):
        x_value = 0.02 + index * 0.193
        y_value = 0.28
        _add_module(axis, (x_value, y_value), 0.165, 0.25, title, gate, facecolor, accent)
        axis.text(x_value + 0.0825, y_value - 0.035, subtitle, ha="center", transform=axis.transAxes, fontsize=5.9, color=PALETTE["slate"])
        if index < len(stages) - 1:
            next_x = 0.02 + (index + 1) * 0.193
            next_y = y_value
            axis.plot([x_value + 0.165, next_x], [y_value + 0.125, next_y + 0.125], transform=axis.transAxes, color=PALETTE["slate"], linewidth=0.8, linestyle=(0, (3, 2)))
            stop_x = (x_value + 0.165 + next_x) / 2
            stop_y = (y_value + next_y) / 2 + 0.125
            axis.scatter([stop_x], [stop_y], transform=axis.transAxes, marker="|", s=120, linewidth=1.5, color=PALETTE["vermilion"], zorder=4)
    axis.text(
        0.5,
        0.025,
        "Dashed connectors indicate dependency, not implication. A failed gate blocks semantic promotion.",
        ha="center",
        transform=axis.transAxes,
        fontsize=6.5,
        color=PALETTE["vermilion"],
        fontweight="bold",
    )
    return _save_figure(fig, output_stem)


def _contract_architecture(output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 3.15), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    axis.text(0.02, 0.94, "EPISTEMIC REPRESENTATION CONTRACT", transform=axis.transAxes, fontsize=8.5, fontweight="bold", color=PALETTE["ink"])
    axis.text(0.02, 0.885, "Typed evidence enters an ordered policy; one decision governs every outward representation.", transform=axis.transAxes, fontsize=6.5, color=PALETTE["slate"])
    _add_module(axis, (0.025, 0.56), 0.18, 0.19, "Typed requested\nclaim", "INPUT 01", PALETTE["blue_pale"], PALETTE["blue"])
    _add_module(axis, (0.025, 0.25), 0.18, 0.19, "Evidence +\ncounterevidence", "INPUT 02", PALETTE["blue_pale"], PALETTE["blue"])
    axis.plot([0.205, 0.25], [0.655, 0.655], transform=axis.transAxes, color=PALETTE["slate"], linewidth=0.9)
    axis.plot([0.205, 0.25], [0.345, 0.345], transform=axis.transAxes, color=PALETTE["slate"], linewidth=0.9)
    axis.plot([0.25, 0.25], [0.345, 0.655], transform=axis.transAxes, color=PALETTE["slate"], linewidth=0.9)
    _add_arrow(axis, (0.25, 0.50), (0.29, 0.50))
    axis.add_patch(Rectangle((0.29, 0.19), 0.32, 0.59, facecolor=PALETTE["ink"], edgecolor="none", transform=axis.transAxes))
    axis.text(0.315, 0.72, f"VERSIONED POLICY {POLICY_VERSION}", transform=axis.transAxes, fontsize=6.4, color="white", fontweight="bold")
    gates = [
        ("01", "Identifiability"),
        ("02", "Provenance"),
        ("03", "Sensitivity / uncertainty / dependence"),
        ("04", "Conflict + policy-specific caveats"),
    ]
    for index, (number, label) in enumerate(gates):
        y_value = 0.62 - index * 0.105
        axis.text(0.32, y_value, number, transform=axis.transAxes, fontsize=5.8, color=PALETTE["gold"], fontweight="bold", va="center")
        axis.text(0.365, y_value, label, transform=axis.transAxes, fontsize=5.3, color="white", va="center")
        axis.plot([0.32, 0.575], [y_value - 0.045, y_value - 0.045], transform=axis.transAxes, color="#415162", linewidth=0.55)
    axis.text(0.315, 0.23, "IDENTIFIABILITY PRECEDES QUALITY GATES", transform=axis.transAxes, fontsize=5.5, color="#AAB6C1", fontweight="bold")
    _add_arrow(axis, (0.61, 0.50), (0.66, 0.50))
    outcomes = [
        (0.66, 0.62, "ADMIT", "statement + encoding", PALETTE["teal"]),
        (0.66, 0.40, "QUALIFY", "scope + caveat", PALETTE["gold"]),
        (0.66, 0.18, "REFUSE", "fallback or block", PALETTE["vermilion"]),
    ]
    for x_value, y_value, decision, consequence, color in outcomes:
        axis.add_patch(Rectangle((x_value, y_value), 0.13, 0.16, facecolor=color, edgecolor="none", transform=axis.transAxes))
        axis.text(x_value + 0.065, y_value + 0.105, decision, ha="center", transform=axis.transAxes, fontsize=6.6, color="white", fontweight="bold")
        axis.text(x_value + 0.065, y_value + 0.04, consequence, ha="center", transform=axis.transAxes, fontsize=5.7, color="white")
        axis.plot([0.61, x_value], [0.50, y_value + 0.08], transform=axis.transAxes, color=color, linewidth=0.9)
    _add_module(axis, (0.83, 0.57), 0.145, 0.17, "Statement +\nvisual", "REPRESENT", PALETTE["teal_pale"], PALETTE["teal"])
    _add_module(axis, (0.83, 0.35), 0.145, 0.17, "Export +\nfallback", "CONTROL", PALETTE["red_pale"], PALETTE["vermilion"])
    _add_module(axis, (0.83, 0.13), 0.145, 0.17, "Witness +\nremediation", "EXPLAIN", PALETTE["mist"], PALETTE["slate"])
    for y_value in (0.655, 0.435, 0.215):
        _add_arrow(axis, (0.79, y_value), (0.83, y_value))
    return _save_figure(fig, output_stem)


def _contract_properties_figure(
    benchmark: dict[str, Any], output_stem: Path
) -> list[Path]:
    checks = benchmark["contract_properties"]["checks"]
    matrix = benchmark["contract_properties"]["falsification_matrix"]
    fig = Figure(figsize=(7.1, 3.05), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    x_positions = (0.02, 0.20, 0.48, 0.75, 0.95)
    for x_value, heading in zip(
        x_positions,
        ("PROPERTY", "ADVERSARIAL PERTURBATION", "FAILURE CONDITION", "CONTROL CONSEQUENCE", "RESULT"),
        strict=True,
    ):
        axis.text(
            x_value, 0.95, heading, transform=axis.transAxes, fontsize=5.7,
            fontweight="bold", color=PALETTE["slate"], va="top"
        )
    for index, row in enumerate(matrix):
        y_value = 0.86 - index * 0.135
        if index % 2 == 0:
            axis.add_patch(Rectangle((0.01, y_value - 0.09), 0.98, 0.125, transform=axis.transAxes, facecolor=PALETTE["mist"], edgecolor="none"))
        key = row["property"].replace("-", "_").replace(" ", "_")
        values = (
            row["property"],
            row["perturbation"],
            row["failure_condition"],
            row.get(
                "contribution_consequence",
                "Joint statement, mark, or export control is violated.",
            ),
        )
        for x_value, text, width in zip(x_positions[:4], values, (21, 34, 31, 28), strict=True):
            words = text.split()
            lines: list[str] = []
            current = ""
            for word in words:
                if current and len(current) + len(word) + 1 > width:
                    lines.append(current)
                    current = word
                else:
                    current = f"{current} {word}".strip()
            if current:
                lines.append(current)
            axis.text(x_value, y_value, "\n".join(lines), transform=axis.transAxes, fontsize=5.6, color=PALETTE["ink"], va="center")
        passed = checks[key]
        axis.text(
            x_positions[4], y_value, "PASS" if passed else "FAIL",
            transform=axis.transAxes, fontsize=5.8, fontweight="bold",
            color=PALETTE["teal"] if passed else PALETTE["vermilion"],
            va="center"
        )
    _panel_title(axis, "A", "Adversarial contract-property matrix")
    return _save_figure(fig, output_stem)


def _policy_lint_mutation_figure(
    benchmark: dict[str, Any], output_stem: Path
) -> list[Path]:
    mutation_result = benchmark.get("policy_lint_mutations", {})
    mutations = mutation_result.get("mutations", [])
    checks = mutation_result.get("check_names", [])
    fig = Figure(figsize=(7.1, 5.4), constrained_layout=True)
    axis = fig.subplots()
    matrix = [
        [1 if mutation["detection_vector"].get(check) else 0 for check in checks]
        for mutation in mutations
    ]
    axis.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        cmap=matplotlib.colors.ListedColormap([PALETTE["mist"], PALETTE["teal"]]),
        vmin=0,
        vmax=1,
    )
    axis.set_xticks(
        range(len(checks)),
        [check.replace("_", " ") for check in checks],
        rotation=52,
        ha="right",
        fontsize=5.3,
    )
    axis.set_yticks(
        range(len(mutations)),
        [mutation["mutation_id"].replace("-", " ") for mutation in mutations],
        fontsize=5.5,
    )
    for row_index, mutation in enumerate(mutations):
        intended_column = checks.index(mutation["intended_check"])
        axis.add_patch(
            Rectangle(
                (intended_column - 0.47, row_index - 0.47),
                0.94,
                0.94,
                fill=False,
                edgecolor=PALETTE["vermilion"],
                linewidth=1.2,
            )
        )
    axis.set_xticks([index - 0.5 for index in range(1, len(checks))], minor=True)
    axis.set_yticks([index - 0.5 for index in range(1, len(mutations))], minor=True)
    axis.grid(which="minor", color="white", linewidth=0.8)
    axis.tick_params(which="both", length=0)
    axis.set_xlabel("Lint invariant (outlined cell = intended target)", fontsize=6.5)
    axis.set_ylabel("Targeted invalid-policy mutation", fontsize=6.5)
    exact_count = mutation_result.get("exact_localization_count", 0)
    axis.set_title(
        f"All {len(mutations)} intended faults detected; {exact_count}/{len(mutations)} localized exactly",
        loc="left",
        fontsize=8.2,
        fontweight="bold",
        color=PALETTE["ink"],
        pad=8,
    )
    return _save_figure(fig, output_stem)


def _governance_state_triptych_figure(
    benchmark: dict[str, Any], output_stem: Path
) -> list[Path]:
    policy_version = benchmark["policy"]["policy_version"]
    fig = Figure(figsize=(7.1, 3.35), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    axis.text(
        0.02,
        0.96,
        "POLICY-DEFINED REFERENCE ASSIGNMENTS",
        transform=axis.transAxes,
        fontsize=8.5,
        fontweight="bold",
        color=PALETTE["ink"],
        va="top",
    )
    axis.text(
        0.02,
        0.89,
        f"Authored Policy {policy_version} assigns these marks and export consequences; perceptual effects are unevaluated.",
        transform=axis.transAxes,
        fontsize=6.5,
        color=PALETTE["slate"],
        va="top",
    )
    states = [
        {
            "x": 0.02,
            "decision": "REFUSE",
            "accent": PALETTE["vermilion"],
            "face": PALETTE["red_pale"],
            "claim": "Causal influence",
            "evidence": "co-occurrence only",
            "encoding": "undirected lexical fallback",
            "export": "causal export blocked",
            "kind": "undirected",
        },
        {
            "x": 0.265,
            "decision": "QUALIFY",
            "accent": PALETTE["gold"],
            "face": PALETTE["gold_pale"],
            "claim": "Conditional asymmetry",
            "evidence": "co-occurrence + prevalence",
            "encoding": "bar-to-ring statistical glyph",
            "export": "qualified statistic only",
            "kind": "conditional",
        },
        {
            "x": 0.51,
            "decision": "QUALIFY",
            "accent": PALETTE["vermilion"],
            "face": PALETTE["red_pale"],
            "claim": "Temporal precedence",
            "evidence": "matched support + conflict",
            "encoding": "interrupted contested relation",
            "export": "ordinary semantic export blocked",
            "kind": "contested",
        },
        {
            "x": 0.755,
            "decision": "ADMIT",
            "accent": PALETTE["teal"],
            "face": PALETTE["teal_pale"],
            "claim": "Event temporal precedence",
            "evidence": "matched event-order annotation",
            "encoding": "solid semantic arrow",
            "export": "scoped temporal claim",
            "kind": "semantic",
        },
    ]
    for state in states:
        x_value = state["x"]
        axis.add_patch(
            Rectangle(
                (x_value, 0.08),
                0.225,
                0.74,
                transform=axis.transAxes,
                facecolor="white",
                edgecolor=PALETTE["line"],
                linewidth=0.8,
            )
        )
        axis.add_patch(
            Rectangle(
                (x_value, 0.70),
                0.225,
                0.12,
                transform=axis.transAxes,
                facecolor=state["accent"],
                edgecolor="none",
            )
        )
        axis.text(
            x_value + 0.018,
            0.76,
            state["decision"],
            transform=axis.transAxes,
            fontsize=7.4,
            fontweight="bold",
            color="white",
            va="center",
        )
        axis.text(
            x_value + 0.018,
            0.65,
            state["claim"],
            transform=axis.transAxes,
            fontsize=7.0,
            fontweight="bold",
            color=PALETTE["ink"],
            va="top",
        )
        axis.text(
            x_value + 0.018,
            0.58,
            f"Observed: {state['evidence']}",
            transform=axis.transAxes,
            fontsize=5.7,
            color=PALETTE["slate"],
            va="top",
        )
        line_y = 0.405
        left_x = x_value + 0.045
        right_x = x_value + 0.18
        axis.scatter(
            [left_x, right_x],
            [line_y, line_y],
            transform=axis.transAxes,
            s=240,
            facecolor=state["face"],
            edgecolor=state["accent"],
            linewidth=1.2,
            zorder=4,
        )
        if state["kind"] == "undirected":
            axis.plot(
                [left_x, right_x],
                [line_y, line_y],
                transform=axis.transAxes,
                color=PALETTE["slate"],
                linewidth=1.7,
                zorder=2,
            )
        elif state["kind"] == "conditional":
            axis.plot(
                [left_x, right_x],
                [line_y, line_y],
                transform=axis.transAxes,
                color="#8A5C00",
                linewidth=1.7,
                linestyle=(0, (4, 3)),
                zorder=2,
            )
            midpoint = (left_x + right_x) / 2
            axis.add_patch(
                Rectangle(
                    (midpoint - 0.025, line_y - 0.035),
                    0.05,
                    0.07,
                    transform=axis.transAxes,
                    facecolor="#FFFAF0",
                    edgecolor=PALETTE["gold"],
                    linewidth=0.8,
                    zorder=5,
                )
            )
            axis.plot(
                [midpoint - 0.016, midpoint - 0.016],
                [line_y - 0.02, line_y + 0.02],
                transform=axis.transAxes,
                color="#8A5C00",
                linewidth=1.5,
                zorder=6,
            )
            axis.scatter(
                [midpoint + 0.014],
                [line_y],
                transform=axis.transAxes,
                s=28,
                facecolor="#FFFAF0",
                edgecolor="#8A5C00",
                linewidth=1.2,
                zorder=6,
            )
        elif state["kind"] == "contested":
            axis.plot(
                [left_x, right_x],
                [line_y, line_y],
                transform=axis.transAxes,
                color=PALETTE["vermilion"],
                linewidth=1.8,
                linestyle=(0, (6, 4, 1, 4)),
                zorder=3,
            )
            midpoint = (left_x + right_x) / 2
            axis.scatter(
                [midpoint],
                [line_y],
                transform=axis.transAxes,
                s=75,
                facecolor="white",
                edgecolor=PALETTE["vermilion"],
                linewidth=1.2,
                marker="X",
                zorder=6,
            )
        else:
            axis.add_patch(
                FancyArrowPatch(
                    (left_x + 0.018, line_y),
                    (right_x - 0.024, line_y),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    linewidth=1.8,
                    color=PALETTE["blue"],
                    transform=axis.transAxes,
                    zorder=3,
                )
            )
        axis.text(
            x_value + 0.1125,
            0.27,
            state["encoding"],
            transform=axis.transAxes,
            fontsize=6.1,
            fontweight="bold",
            color=state["accent"],
            ha="center",
        )
        axis.text(
            x_value + 0.1125,
            0.17,
            state["export"],
            transform=axis.transAxes,
            fontsize=5.8,
            color=PALETTE["slate"],
            ha="center",
        )
    return _save_figure(fig, output_stem)


def _inspector_composite_figure(
    figure_root: Path, output_stem: Path
) -> list[Path]:
    decision_path = figure_root / "inspector_policy27_decision_crop.png"
    evidence_path = figure_root / "inspector_policy27_evidence_crop.png"
    encoding_path = figure_root / "inspector_policy27_encoding_crop.png"
    if not all(path.is_file() for path in (decision_path, evidence_path, encoding_path)):
        return []
    for path in (
        figure_root / "inspector_policy27_screenshot.png",
        decision_path,
        evidence_path,
        encoding_path,
    ):
        if path.is_file():
            with Image.open(path) as image:
                image.save(path, dpi=(600, 600))
    evidence = imread(evidence_path)
    evidence_split = round(evidence.shape[1] * 0.582)
    encoding = imread(encoding_path)
    encoding_height = round(encoding.shape[0] * 0.28)
    captures = {
        "A": (imread(decision_path), "Requested claim, decision, and authorization"),
        "B": (
            encoding[:encoding_height],
            "Representation: no authorized relation",
        ),
        "C": (
            evidence[:, evidence_split + 1 :],
            "Projection, gates, witness, and remediation",
        ),
    }
    fig = Figure(figsize=(7.1, 5.0))
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 1.65))
    axes = {
        "A": fig.add_subplot(grid[0, 0]),
        "B": fig.add_subplot(grid[0, 1]),
        "C": fig.add_subplot(grid[1, :]),
    }
    fig.subplots_adjust(
        left=0.02,
        right=0.98,
        bottom=0.02,
        top=0.91,
        wspace=0.06,
        hspace=0.20,
    )
    fig.text(
        0.5,
        0.975,
        "1 REQUEST  >  2 EVIDENCE  >  3 DECISION  >  4 REPRESENTATION  >  5 REMEDIATION",
        ha="center",
        va="top",
        fontsize=7.2,
        fontweight="bold",
        color=PALETTE["ink"],
    )
    for panel, (image, title) in captures.items():
        axis = axes[panel]
        axis.imshow(image)
        axis.set_axis_off()
        _panel_title(axis, panel, title)
    return _save_figure(fig, output_stem)


def _governed_walkthrough_figure(output_stem: Path) -> list[Path]:
    fig = Figure(figsize=(7.1, 3.35), constrained_layout=True)
    axis = fig.subplots()
    axis.set_axis_off()
    rows = [
        ("01", "Lexical only", "REFUSE semantic", "Undirected fallback", "Add matched annotation", PALETTE["vermilion"], PALETTE["red_pale"]),
        ("02", "Matched positive", "ADMIT equivalence", "Undirected semantic", "No remediation", PALETTE["teal"], PALETTE["teal_pale"]),
        ("03", "Negative evidence", "REFUSE positive", "No semantic relation", "Inspect counterevidence", PALETTE["vermilion"], PALETTE["red_pale"]),
        ("04", "Bootstrap missing", "REFUSE stability", "No stability claim", "Run cluster bootstrap", PALETTE["vermilion"], PALETTE["red_pale"]),
    ]
    columns = [0.08, 0.31, 0.52, 0.74]
    headings = ["Evidence state", "Decision", "Export consequence", "Remediation"]
    axis.text(0.02, 0.955, "GOVERNED INSPECTOR STATE MATRIX", transform=axis.transAxes, fontsize=8.5, fontweight="bold", color=PALETTE["ink"])
    axis.text(0.02, 0.895, "Evidence changes decision, visible encoding, export, and next action as one coupled state.", transform=axis.transAxes, fontsize=6.5, color=PALETTE["slate"])
    for x_value, heading in zip(columns, headings, strict=True):
        axis.text(
            x_value,
            0.79,
            heading,
            transform=axis.transAxes,
            fontsize=6.2,
            fontweight="bold",
            color=PALETTE["gray"],
        )
    for index, row in enumerate(rows):
        y_value = 0.67 - index * 0.155
        axis.add_patch(Rectangle((0.02, y_value - 0.055), 0.96, 0.12, facecolor=row[6], edgecolor="none", transform=axis.transAxes))
        axis.add_patch(Rectangle((0.02, y_value - 0.055), 0.012, 0.12, facecolor=row[5], edgecolor="none", transform=axis.transAxes))
        axis.text(0.047, y_value + 0.005, row[0], transform=axis.transAxes, fontsize=6.2, fontweight="bold", color=row[5], va="center")
        for x_value, text in zip(columns, row[1:5], strict=True):
            axis.text(
                x_value,
                y_value + 0.005,
                text,
                transform=axis.transAxes,
                fontsize=6.7,
                va="center",
                color=PALETTE["ink"],
                fontweight="bold" if x_value == columns[1] else "normal",
            )
        axis.plot([0.285, 0.285], [y_value - 0.035, y_value + 0.045], transform=axis.transAxes, color=PALETTE["line"], linewidth=0.55)
        axis.plot([0.495, 0.495], [y_value - 0.035, y_value + 0.045], transform=axis.transAxes, color=PALETTE["line"], linewidth=0.55)
        axis.plot([0.715, 0.715], [y_value - 0.035, y_value + 0.045], transform=axis.transAxes, color=PALETTE["line"], linewidth=0.55)
    axis.text(
        0.5,
        0.035,
        "The requested claim remains attached to every fallback or blocked export; no stronger semantics are silently substituted.",
        ha="center",
        transform=axis.transAxes,
        fontsize=6.4,
        color=PALETTE["vermilion"],
        fontweight="bold",
    )
    return _save_figure(fig, output_stem)


def _artifact_record(
    root: Path,
    artifact_id: str,
    kind: str,
    files: list[Path],
    source_inputs: list[str],
    status: str,
    caption: str,
    alt_text: str = "",
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "kind": kind,
        "files": [path.relative_to(root).as_posix() for path in files],
        "source_inputs": source_inputs,
        "status": status,
        "caption": caption,
        "alt_text": alt_text,
    }


def _write_empirical_results(
    path: Path,
    summary: dict[str, Any],
    audit: dict[str, Any],
    external: dict[str, Any],
    specification: dict[str, Any],
    corpus_rows: list[dict[str, Any]],
    threshold_rows: list[dict[str, Any]],
) -> None:
    external_datasets = external["datasets"]
    external_total = sum(
        dataset["record_count"] for dataset in external_datasets.values()
    )
    paws = external_datasets["paws"]
    paws_high_overlap = paws["lexical_overlap"][
        "high_overlap_non_paraphrase_count"
    ]
    paws_negative = paws["label_counts"]["non_paraphrase"]
    lines = [
        "# Empirical Results for Manuscript Development",
        "",
        "## Evidence Boundary",
        "",
        (
            "These results were generated from maintained code and machine-readable "
            "outputs. The first author attests that the job-ad workbook combines a "
            "single cross-sectional scrape from Glassdoor and SimplyHired in June 2023. "
            "Embedded workbook metadata supports file authorship in part. Public release "
            "under CC BY 4.0 is planned but no public deposit URL is yet recorded. The "
            "sampling frame and per-row source platform are unavailable, so the dataset "
            "does not support population-level labor-market or platform-comparison inference."
        ),
        "",
        "## Workbook Audit",
        "",
        f"- Rows audited: {audit['row_count']:,}.",
        (
            f"- Missing Description values: {audit['null_counts']['Description']:,} "
            f"({audit['null_rates']['Description']:.3%})."
        ),
        (
            "- Duplicate complete rows beyond the first: "
            f"{audit['exact_duplicate_row_instances']:,} "
            f"({audit['exact_duplicate_row_instances'] / audit['row_count']:.2%})."
        ),
        (
            "- Duplicate Description instances beyond the first: "
            f"{audit['exact_duplicate_description_instances']:,} "
            f"({audit['exact_duplicate_description_instances'] / audit['row_count']:.2%})."
        ),
        "- The workbook does not include a Skills field or a per-row source-platform field.",
        "",
        "## Default Structural Results",
        "",
        "| Corpus | Documents | Units | Nodes | Edges | SCCs | Largest SCC | Asymmetric edges |",
        "| ------ | ---------: | ----: | ----: | ----: | ---: | ----------: | ---------------: |",
    ]
    for row in corpus_rows:
        lines.append(
            f"| {row['corpus']} | {row['documents']} | {row['units']} | "
            f"{row['nodes']} | {row['edges']} | {row['scc_count']} | "
            f"{row['largest_scc']} | {row['asymmetric_edge_rate']:.1%} |"
        )
    row_by_corpus = {row["corpus"]: row for row in corpus_rows}
    raw_jobs = row_by_corpus.get("glassdoor_simplyhired_jobs")
    unique_jobs = row_by_corpus.get(
        "glassdoor_simplyhired_jobs_unique_descriptions"
    )
    if raw_jobs and unique_jobs:
        lines.extend(
            [
                "",
                "## Duplication Sensitivity",
                "",
                (
                    f"Exact normalized-description deduplication retained "
                    f"{unique_jobs['documents']:,} of {raw_jobs['documents']:,} documents "
                    f"({unique_jobs['documents'] / raw_jobs['documents']:.1%}). Extracted "
                    f"units fell from {raw_jobs['units']:,} to {unique_jobs['units']:,}, "
                    f"retained edges from {raw_jobs['edges']} to {unique_jobs['edges']}, "
                    f"and the default largest SCC from {raw_jobs['largest_scc']} to "
                    f"{unique_jobs['largest_scc']} nodes. This comparison demonstrates "
                    "that duplicate handling changes measured graph structure and must be "
                    "reported as an analysis decision."
                ),
            ]
        )
    lines.extend(["", "## Threshold Sensitivity", ""])
    for name in summary["corpora"]:
        values = [row for row in threshold_rows if row["corpus"] == name]
        if not values:
            continue
        largest = [row["largest_scc"] for row in values]
        edges = [row["edges"] for row in values]
        lines.append(
            f"- {name}: largest SCC ranges from {min(largest)} to {max(largest)} "
            f"nodes; retained edges range from {min(edges)} to {max(edges)}."
        )
    lines.extend(
        [
            "",
            "## Direction and Claim Boundary",
            "",
            (
                "Global edge reversal preserves every SCC partition by graph-theoretic "
                "invariance. In the current unordered co-occurrence model, confidence "
                "orientation is determined by marginal prevalence. These results support "
                "descriptive lexical association and structural sensitivity claims only. "
                "They do not establish semantic direction, themes, causality, analyst "
                "benefit, or labor-market conditions."
            ),
            "",
            "## External Construct-Matched Policy Stress Tests",
            "",
            (
                f"Five external datasets contribute {external_total:,} annotated or "
                "derived relation records across equivalence, directional entailment, "
                "prerequisite direction, and event temporal precedence. AL-CPL contains "
                f"{external_datasets['al_cpl']['record_count']:,} candidate concept pairs "
                f"with {external_datasets['al_cpl']['label_counts']['prerequisite']:,} "
                "positive prerequisite annotations. TORQUE contributes "
                f"{external_datasets['torque']['record_count']:,} usable relations from "
                "adjudicated dev annotations; public test answers were excluded. Matched "
                "annotations were admitted, while insufficiency, counterevidence, mention "
                "order, and unsupported reversal were refused. Cross-construct admission "
                "was zero."
            ),
            (
                f"PAWS contains {paws_high_overlap:,} high-overlap non-paraphrases among "
                f"{paws_negative:,} negative labels "
                f"({paws_high_overlap / paws_negative:.3%}), directly demonstrating why "
                "lexical overlap cannot serve "
                "as generic semantic evidence. These are policy-transition results, not "
                "predictive-model accuracy, universal relation truth, causal validity, "
                "human-benefit evidence, or normative policy validation. No raw sentence "
                "pairs, questions, passages, or concept pairs are redistributed."
            ),
            "",
            "## Expanded Specification Surface",
            "",
        ]
    )
    for name, result in specification["corpora"].items():
        geometry = result["edge_set_geometry"]
        consequences = result["certificate_consequences"]
        lines.append(
            f"- {name}: {result['configuration_count']} configurations; "
            f"{geometry['intersection_count']:,} intersection edges, "
            f"{geometry['union_count']:,} union edges, "
            f"{geometry['emergent_count']:,} emergent edges; "
            f"{consequences['admitted_union_edges']:,} union edges admitted and "
            f"{consequences['qualified_union_edges']:,} qualified at the 0.80 gate; "
            f"the default-reference split is "
            f"{consequences['admitted_default_edges']:,}/"
            f"{consequences['qualified_default_edges']:,}."
        )
    lines.extend(
        [
            "",
            "## Runtime Boundary",
            "",
            (
                "Wall time and traced Python allocation are measurements from the recorded "
                "Windows and Python environment. They are descriptive, not hardware-neutral "
                "benchmarks."
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="ascii")


def _write_inventory(path: Path, artifacts: list[dict[str, Any]]) -> None:
    lines = [
        "# Publication Artifact Inventory",
        "",
        (
            "All quantitative artifacts are generated from the source inputs listed in "
            "`manifest.json`. Raw job-ad text is excluded."
        ),
        "",
        "| ID | Kind | Status | Files |",
        "| -- | ---- | ------ | ----- |",
    ]
    for artifact in artifacts:
        files = ", ".join(artifact["files"])
        lines.append(
            f"| {artifact['id']} | {artifact['kind']} | {artifact['status']} | {files} |"
        )
    lines.extend(["", "## Captions and Alt Text", ""])
    for artifact in artifacts:
        lines.extend(
            [
                f"### {artifact['id']}",
                "",
                f"Caption: {artifact['caption']}",
                "",
                f"Alt text: {artifact.get('alt_text') or 'Not applicable.'}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="ascii")


def build_publication_artifacts(root: Path) -> dict[str, Any]:
    summary_path = root / "results" / "research_evaluation_summary.json"
    audit_path = root / "results" / "glassdoor_simplyhired_jobs_audit.json"
    benchmark_path = root / "results" / "claim_admissibility_benchmark.json"
    specification_path = root / "results" / "specification_surface.json"
    external_path = root / "results" / "external_validation.json"
    summary = _read_json(summary_path)
    audit = _read_json(audit_path)
    benchmark = _read_json(benchmark_path)
    specification = _read_json(specification_path)
    external = _read_json(external_path)
    policy_version = benchmark["policy"]["policy_version"]
    mutation_count = benchmark.get("policy_lint_mutations", {}).get("mutation_count", 0)

    output_root = root / "artifacts"
    data_root = output_root / "data"
    table_root = output_root / "tables"
    figure_root = output_root / "figures"
    mapping_root = output_root / "mappings"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "job_ads_audit.json").unlink(missing_ok=True)
    corpus_rows = corpus_overview_rows(summary)
    quality_rows = job_ads_quality_rows(audit)
    threshold_rows = threshold_sensitivity_rows(summary)
    compact_threshold_rows = threshold_table_rows(threshold_rows)

    corpus_payloads = {}
    corpus_result_paths = {}
    for name in summary["corpora"]:
        corpus_path = root / "results" / "evaluation_corpora" / f"{name}.json"
        if corpus_path.exists():
            corpus_payloads[name] = _read_json(corpus_path)
            corpus_result_paths[name] = corpus_path
    edge_rows = edge_distribution_rows(corpus_payloads)
    benchmark_rows = claim_benchmark_rows(benchmark)
    policy_claim_summary_rows = policy_claim_rows(benchmark)
    property_rows = contract_property_rows(benchmark)
    policy_lint_rows = [
        {"check": name.replace("_", " "), "passed": "yes" if passed else "no"}
        for name, passed in benchmark["policy_lint"]["checks"].items()
    ]
    mutation_rows = policy_lint_mutation_rows(benchmark)
    mutation_family_rows = policy_lint_mutation_family_rows(benchmark)
    enforcement_rows = representation_enforcement_rows(benchmark)
    ablation_rows = architecture_ablation_rows(benchmark)
    necessity_rows = contract_necessity_rows(benchmark)
    duplication_rows = [benchmark["controlled_duplication_stress"]]
    external_rows = external_validation_rows(external)
    specification_rows = specification_surface_rows(specification)

    corpus_csv = table_root / "corpus_overview.csv"
    quality_csv = table_root / "job_ads_quality.csv"
    threshold_csv = table_root / "threshold_sensitivity.csv"
    edge_csv = table_root / "edge_distributions.csv"
    benchmark_csv = table_root / "claim_admissibility_benchmark.csv"
    property_csv = table_root / "contract_properties.csv"
    policy_lint_csv = table_root / "policy_lint.csv"
    policy_claim_csv = table_root / "policy_claim_types.csv"
    mutation_csv = table_root / "policy_lint_mutations.csv"
    mutation_family_csv = table_root / "policy_lint_mutation_families.csv"
    enforcement_csv = table_root / "representation_enforcement.csv"
    ablation_csv = table_root / "architecture_enforcement_ablation.csv"
    necessity_csv = table_root / "contract_field_necessity.csv"
    duplication_csv = table_root / "controlled_duplication_stress.csv"
    external_csv = table_root / "external_validation.csv"
    specification_csv = table_root / "specification_surface.csv"
    manuscript_statistics = table_root / "manuscript_statistics.tex"
    _write_csv(corpus_csv, corpus_rows)
    _write_csv(quality_csv, quality_rows)
    _write_csv(threshold_csv, threshold_rows)
    if edge_rows:
        _write_csv(edge_csv, edge_rows)
    _write_csv(benchmark_csv, benchmark_rows)
    _write_csv(property_csv, property_rows)
    _write_csv(policy_lint_csv, policy_lint_rows)
    if policy_claim_summary_rows:
        _write_csv(policy_claim_csv, policy_claim_summary_rows)
    if mutation_rows:
        _write_csv(mutation_csv, mutation_rows)
        _write_csv(mutation_family_csv, mutation_family_rows)
    if enforcement_rows:
        _write_csv(enforcement_csv, enforcement_rows)
    if ablation_rows:
        _write_csv(ablation_csv, ablation_rows)
    if necessity_rows:
        _write_csv(necessity_csv, necessity_rows)
    _write_csv(duplication_csv, duplication_rows)
    _write_csv(external_csv, external_rows)
    _write_csv(specification_csv, specification_rows)
    _write_manuscript_statistics(manuscript_statistics, specification)

    table_specs = [
        (
            table_root / "corpus_overview.tex",
            corpus_rows,
            [
                ("corpus", "Corpus", "l"),
                ("documents", "Documents", "r"),
                ("units", "Units", "r"),
                ("nodes", "Nodes", "r"),
                ("edges", "Edges", "r"),
                ("scc_count", "SCCs", "r"),
                ("largest_scc", "Largest SCC", "r"),
                ("asymmetric_edge_rate", "Asymmetric", "r"),
            ],
            "Measured corpus and graph structure under the default configuration.",
            "tab:corpus-overview",
        ),
        (
            table_root / "job_ads_quality.tex",
            quality_rows,
            [("measure", "Measure", "l"), ("count", "Count", "r"), ("rate", "Rate", "r")],
            "Quality indicators from all rows in the combined Glassdoor and SimplyHired workbook.",
            "tab:job-ads-quality",
        ),
        (
            table_root / "threshold_sensitivity.tex",
            compact_threshold_rows,
            [
                ("corpus", "Corpus", "l"),
                ("min_confidence", "Min. confidence", "r"),
                ("lift_range", "Lift range", "r"),
                ("edges", "Edges", "r"),
                ("scc_count", "SCCs", "r"),
                ("largest_scc", "Largest SCC", "r"),
            ],
            (
                "Structural sensitivity across the prespecified threshold grid. "
                "A lift range indicates identical results at 1.00, 1.05, and 1.25; "
                "individual values are retained where outcomes differ."
            ),
            "tab:threshold-sensitivity",
        ),
    ]
    if edge_rows:
        table_specs.append(
            (
                table_root / "edge_distributions.tex",
                edge_rows,
                [
                    ("corpus", "Corpus", r"@{}l"),
                    ("edge_count", "Edges", "r"),
                    ("confidence_median", "Median confidence", "r"),
                    ("support_median", "Median support", "r"),
                    ("lift_median", "Median lift", "r"),
                    ("shown_evidence_median", "Median shown evidence", "r"),
                ],
                "Median retained-edge statistics under the default configuration.",
                "tab:edge-distributions",
            )
        )
    table_specs.extend(
        [
            (
                table_root / "claim_admissibility_benchmark.tex",
                benchmark_rows,
                [
                    ("case", "Controlled case", r"@{}p{.10\textwidth}"),
                    ("claim", "Requested claim", r"p{.10\textwidth}"),
                    ("observed", "Decision", r"p{.055\textwidth}"),
                    ("observed_evidence", "Observed evidence", r"p{.10\textwidth}"),
                    ("decision_reason", "Controlling reason", r"p{.10\textwidth}"),
                    ("triggered_reasons", "All triggered reasons", r"p{.13\textwidth}"),
                    ("encoding", "Representation", r"p{.09\textwidth}"),
                    ("requested_claim_export", "Export", r"p{.055\textwidth}"),
                    ("witness", "Exact witness", r"p{.20\textwidth}@{}"),
                ],
                "Policy decisions, complete typed reasons, and representation consequences in the controlled benchmark; all observed decisions equal their authored expectations.",
                "tab:claim-benchmark",
            ),
            (
                table_root / "contract_properties.tex",
                property_rows,
                [("property", "Executable property", "l"), ("passed", "Passed", "l")],
                f"Executable policy-contract properties under policy version {policy_version}.",
                "tab:contract-properties",
            ),
            (
                table_root / "policy_lint.tex",
                policy_lint_rows,
                [("check", "Policy lint check", "l"), ("passed", "Passed", "l")],
                f"Structural and behavioral policy-lint results for Policy {policy_version}.",
                "tab:policy-lint",
            ),
            (
                table_root / "controlled_duplication_stress.tex",
                duplication_rows,
                [
                    ("base_source_count", "Sources", "r"),
                    ("row_count", "Rows", "r"),
                    ("duplicate_rows_beyond_first", "Duplicate rows", "r"),
                    ("duplicate_rate", "Duplicate rate", "r"),
                    ("naive_support_inflation_factor", "Support inflation", "r"),
                ],
                "Generated duplication stress case with no third-party text.",
                "tab:controlled-duplication",
            ),
            (
                table_root / "external_validation.tex",
                external_rows,
                [
                    ("dataset", "Dataset", r"@{}p{.07\textwidth}"),
                    ("evidence_condition", "Evidence condition", r"p{.16\textwidth}"),
                    ("requested_claim", "Requested claim", r"p{.15\textwidth}"),
                    ("expected_consequence", "Expected", r"p{.08\textwidth}"),
                    ("observed_consequence", "Observed", r"p{.08\textwidth}"),
                    ("failure_or_authorization_path", "Failure / authorization path", r"p{.24\textwidth}@{}"),
                ],
                (
                    f"Deterministic construct-boundary Policy {policy_version} transition map. Rows "
                    "show evidence condition, requested claim, expected and observed policy "
                    "consequences, and the exercised failure or authorization path; they are "
                    "conformance routes, not predictive accuracy estimates. Cross-construct "
                    "rows compact exact typed requests retained with counts and route IDs in "
                    "the artifact manifest."
                ),
                "tab:external-validation",
            ),
            (
                table_root / "specification_surface.tex",
                specification_rows,
                [
                    ("corpus", "Corpus", "l"),
                    ("configurations", "Cfg.", "r"),
                    ("interactions", "2-factor cfgs.", "r"),
                    ("default_edges", "Default", "r"),
                    ("union_edges", "Union", "r"),
                    ("minimum_survival", "Min.", "r"),
                    ("mean_survival", "Mean", "r"),
                    ("default_mean_survival", "Default mean", "r"),
                    ("one_to_one_component_overlap", "1:1 comp. J", "r"),
                    ("admitted_union_edges", "Meets pers. gate", "r"),
                    ("qualified_union_edges", "Below pers. gate", r"r@{}"),
                ],
                (
                    "Union-edge persistence, set geometry, and one-to-one component overlap over an "
                    "unweighted 24-configuration surface including six bounded interactions; "
                    "the final columns report outcomes relative to the prespecified 0.80 persistence gate."
                ),
                "tab:specification-surface",
            ),
        ]
    )
    if mutation_rows:
        table_specs.append(
            (
                table_root / "policy_lint_mutations.tex",
                mutation_family_rows,
                [
                    ("mutation_family", "Mutation family", r"@{}p{.27\textwidth}"),
                    ("targeted_mutations", "Targeted", r"p{.09\textwidth}"),
                    ("detected", "Detected", r"p{.09\textwidth}"),
                    ("result", "Result", r"p{.16\textwidth}"),
                    ("artifact_detail", "Artifact", r"p{.28\textwidth}@{}"),
                ],
                f"Family-level summary of {mutation_count} targeted Policy {policy_version} lint mutations; the artifact retains every row and trigger vector.",
                "tab:policy-lint-mutations",
            )
        )
    if enforcement_rows:
        table_specs.append(
            (
                table_root / "representation_enforcement.tex",
                enforcement_rows,
                [
                    ("state", "Certificate state", r"@{}p{.12\textwidth}"),
                    ("decision", "Decision", r"p{.06\textwidth}"),
                    ("decision_reason", "Controlling reason", r"p{.12\textwidth}"),
                    ("permitted_statement", "Permitted statement", r"p{.12\textwidth}"),
                    ("mark", "Mark", r"p{.12\textwidth}"),
                    ("requested_claim_export", "Export", r"p{.07\textwidth}"),
                    ("fallback", "Fallback", r"p{.10\textwidth}"),
                    ("witness", "Witness", r"p{.07\textwidth}"),
                    ("remediation", "Remediation", r"p{.08\textwidth}"),
                    ("conforms", "Conforms", r"p{.06\textwidth}@{}"),
                ],
                f"Certificate-to-representation enforcement under Policy {policy_version}.",
                "tab:representation-enforcement",
            )
        )
    if ablation_rows:
        table_specs.append(
            (
                table_root / "architecture_enforcement_ablation.tex",
                ablation_rows,
                [
                    ("architecture", "Output-control condition", r"@{}p{.25\textwidth}"),
                    ("unauthorized_statements", "Statements", "r"),
                    ("unauthorized_marks", "Marks", "r"),
                    ("unauthorized_exports", "Exports", "r"),
                    ("lawful_fallbacks", "Fallbacks", r"r@{}"),
                ],
                (
                    "Output reachability for three generated adversarial fixtures "
                    "under four output-control conditions. Unauthorized means not authorized "
                    f"under Policy {policy_version} for the supplied claim/evidence fixture. "
                    "Each numeric entry is a count out of the three fixtures. A fallback only "
                    "listed in certificate metadata is not reachable unless emitted, selectable, "
                    "renderable, or exportable as an output. "
                    "The ablation isolates enforcement: it does not compare human effectiveness "
                    "or characterize all warning or inspection systems. Eight maintained "
                    "certificate-guarded output entry points are audited separately, not as "
                    "a 24-case cross-product."
                ),
                "tab:architecture-ablation",
            )
        )
    if necessity_rows:
        table_specs.append(
            (
                table_root / "contract_field_necessity.tex",
                necessity_rows,
                [
                    ("contract_distinction", "Removed distinction", r"@{}p{.16\textwidth}"),
                    ("invalid_behavior_enabled", "Invalid behavior enabled", r"p{.38\textwidth}"),
                    ("joint_control_consequence", "Joint-control consequence", r"p{.28\textwidth}"),
                    ("detected", "Detected", r"p{.05\textwidth}@{}"),
                ],
                (
                    "One-at-a-time contract-field removals and corruptions with their "
                    "reachable invalid behavior; these probes establish implementation "
                    "necessity, not ontological minimality."
                ),
                "tab:contract-field-necessity",
            )
        )
    for path, rows, columns, caption, label in table_specs:
        _write_latex_table(path, rows, columns, caption, label)
    if policy_claim_summary_rows:
        _write_policy_claim_table(table_root, policy_claim_summary_rows, policy_version)

    summary_snapshot = data_root / summary_path.name
    audit_snapshot = data_root / audit_path.name
    benchmark_snapshot = data_root / benchmark_path.name
    specification_snapshot = data_root / specification_path.name
    external_snapshot = data_root / external_path.name
    policy_version_slug = "_".join(policy_version.split(".")[:2])
    policy_snapshot = data_root / f"themegraph_policy_{policy_version_slug}.json"
    (data_root / "themegraph_policy_2_4.json").unlink(missing_ok=True)
    (data_root / "themegraph_policy_2_3.json").unlink(missing_ok=True)
    (data_root / "themegraph_policy_2_2.json").unlink(missing_ok=True)
    shutil.copyfile(summary_path, summary_snapshot)
    shutil.copyfile(audit_path, audit_snapshot)
    shutil.copyfile(benchmark_path, benchmark_snapshot)
    shutil.copyfile(specification_path, specification_snapshot)
    shutil.copyfile(external_path, external_snapshot)
    policy_snapshot.write_text(
        json.dumps(benchmark["policy"], indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )

    job_figure = _job_ads_quality_figure(quality_rows, figure_root / "job_ads_quality")
    structure_figure = _corpus_structure_figure(
        corpus_rows, figure_root / "cross_corpus_structure"
    )
    threshold_figure = _threshold_sensitivity_figure(
        threshold_rows, figure_root / "threshold_sensitivity"
    )
    performance_figure = _performance_figure(
        corpus_rows, figure_root / "measured_performance"
    )
    edge_figure = (
        _edge_distribution_figure(edge_rows, figure_root / "edge_distributions")
        if edge_rows
        else []
    )
    benchmark_figure = _claim_benchmark_figure(
        benchmark, figure_root / "claim_admissibility_benchmark"
    )
    transition_figure = _evidence_transition_figure(
        benchmark, mapping_root / "evidence_transition"
    )
    specification_figure = _specification_survival_figure(
        specification, figure_root / "specification_survival"
    )
    external_figure = _external_validation_figure(
        external, figure_root / "external_validation"
    )
    claim_mapping = _claim_admissibility_mapping(
        mapping_root / "claim_admissibility_observation_map"
    )
    pipeline_mapping = _pipeline_mapping(mapping_root / "empirical_artifact_pipeline")
    overview_architecture = _themegraph_overview_architecture(
        mapping_root / "themegraph_overview_architecture"
    )
    dependency_ladder = _epistemic_dependency_ladder(
        mapping_root / "epistemic_dependency_ladder"
    )
    contract_architecture = _contract_architecture(
        mapping_root / "contract_architecture"
    )
    contract_properties_figure = _contract_properties_figure(
        benchmark, figure_root / "contract_properties"
    )
    policy_mutation_figure = (
        _policy_lint_mutation_figure(
            benchmark, figure_root / "policy_lint_mutations"
        )
        if mutation_rows
        else []
    )
    governance_triptych = _governance_state_triptych_figure(
        benchmark, figure_root / "governance_state_triptych"
    )
    inspector_composite = _inspector_composite_figure(
        figure_root, figure_root / "inspector_policy27_composite"
    )
    governed_walkthrough = _governed_walkthrough_figure(
        mapping_root / "governed_inspector_walkthrough"
    )
    for obsolete_name in (
        "inspector_policy21_screenshot.png",
        "inspector_policy22_screenshot.png",
        "inspector_policy23_screenshot.png",
        "inspector_policy23_contract_crop.png",
        "inspector_policy24_screenshot.png",
        "inspector_policy24_contract_crop.png",
        "inspector_policy25_screenshot.png",
        "inspector_policy26_screenshot.png",
        "inspector_policy26_decision_crop.png",
        "inspector_policy26_evidence_crop.png",
        "inspector_policy26_encoding_crop.png",
    ):
        (figure_root / obsolete_name).unlink(missing_ok=True)

    summary_input = summary_path.relative_to(root).as_posix()
    audit_input = audit_path.relative_to(root).as_posix()
    benchmark_input = benchmark_path.relative_to(root).as_posix()
    specification_input = specification_path.relative_to(root).as_posix()
    external_input = external_path.relative_to(root).as_posix()
    corpus_inputs = [path.relative_to(root).as_posix() for path in corpus_result_paths.values()]
    artifacts = [
        _artifact_record(root, "data-evaluation-summary", "data", [summary_snapshot], [summary_input], "observed", "Validated multi-corpus evaluation summary."),
        _artifact_record(root, "data-job-ads-audit", "data", [audit_snapshot], [audit_input], "observed", "Full workbook quality audit without source text."),
        _artifact_record(root, "data-claim-admissibility-benchmark", "data", [benchmark_snapshot], [benchmark_input], "observed", "Controlled claim-policy benchmark and evidence-transition results."),
        _artifact_record(root, "data-specification-surface", "data", [specification_snapshot], [specification_input], "observed", "Multi-axis specification-surface results."),
        _artifact_record(root, "data-external-validation", "data", [external_snapshot], [external_input], "observed", "Aggregate-only MRPC, PAWS, SNLI, AL-CPL, and TORQUE policy stress-test results."),
        _artifact_record(root, f"data-policy-{policy_version_slug.replace('_', '-')}", "data", [policy_snapshot], [benchmark_input], "derived", f"Declarative Policy {policy_version} claim, governed-object signature, predicate, adjudication requirement, pair scope, encoding, fallback, and remediation schema."),
        _artifact_record(root, "table-corpus-overview", "table", [corpus_csv, table_root / "corpus_overview.tex"], [summary_input], "observed", "Corpus and default graph structure."),
        _artifact_record(root, "table-job-ads-quality", "table", [quality_csv, table_root / "job_ads_quality.tex"], [audit_input], "observed", "Measured workbook quality indicators."),
        _artifact_record(root, "table-threshold-sensitivity", "table", [threshold_csv, table_root / "threshold_sensitivity.tex"], [summary_input], "observed", "Full prespecified confidence and lift threshold grid."),
        _artifact_record(root, "table-claim-admissibility-benchmark", "table", [benchmark_csv, table_root / "claim_admissibility_benchmark.tex"], [benchmark_input], "observed", "Case-level expected and observed claim-policy decisions."),
        _artifact_record(root, "table-contract-properties", "table", [property_csv, table_root / "contract_properties.tex"], [benchmark_input], "observed", "Executable contract-property conformance results."),
        _artifact_record(root, "table-policy-lint", "table", [policy_lint_csv, table_root / "policy_lint.tex"], [benchmark_input], "observed", f"Structural and behavioral Policy {policy_version} lint results."),
        _artifact_record(root, "table-controlled-duplication", "table", [duplication_csv, table_root / "controlled_duplication_stress.tex"], [benchmark_input], "observed", "Generated duplication/dependence stress case without third-party text."),
        _artifact_record(root, "table-external-validation", "table", [external_csv, table_root / "external_validation.tex"], [external_input], "observed", "Construct-matched aggregate policy stress testing across five datasets and four epistemic functions."),
        _artifact_record(root, "table-specification-surface", "table", [specification_csv, table_root / "specification_surface.tex"], [specification_input], "observed", "Union-edge geometry, one-to-one component overlap, and certificate consequences across 24 configurations."),
        _artifact_record(root, "manuscript-statistics", "manuscript-source", [manuscript_statistics], [specification_input], "derived", "Authoritative ACM specification-surface values exposed as LaTeX macros."),
        _artifact_record(
            root,
            "figure-job-ads-quality",
            "figure",
            job_figure,
            [audit_input],
            "observed",
            (
                f"Quality indicators from all {audit['row_count']:,} author-collected "
                "Glassdoor and SimplyHired workbook rows."
            ),
            (
                "Horizontal bars show the missing-description rate, duplicate complete-row "
                "rate, and duplicate-description rate."
            ),
        ),
        _artifact_record(root, "figure-cross-corpus-structure", "figure", structure_figure, [summary_input], "observed", "Default graph size, largest SCC, and retained-edge asymmetry across evaluated corpora.", "Three aligned panels compare node and edge counts, largest SCC size, and asymmetric-edge share across the raw jobs, unique-description jobs, synthetic, O*NET, ACM text, and Python standard-library corpora."),
        _artifact_record(root, "figure-threshold-sensitivity", "figure", threshold_figure, [summary_input], "observed", "Largest SCC size across the prespecified confidence and lift grid for five nonsynthetic corpora.", "Five heatmaps show largest SCC size at nine threshold combinations for all job rows, unique job descriptions, O*NET, ACM text, and Python standard-library text."),
        _artifact_record(root, "figure-measured-performance", "figure", performance_figure, [summary_input], "observed", "Measured core wall time and traced Python allocation in the recorded environment.", "Two logarithmic scatter plots relate extracted text-unit count to wall time and peak traced Python allocation."),
        _artifact_record(root, "figure-claim-admissibility-benchmark", "figure", benchmark_figure, [benchmark_input], "observed", "Controlled claim-admissibility decisions and representation consequences.", "Nine horizontal decision bars show admitted, qualified, and refused claims, including fallback encodings where available."),
        _artifact_record(root, "mapping-evidence-transition", "mapping", transition_figure, [benchmark_input], "observed", "Evidence augmentation changes an explicit prerequisite claim from refusal with undirected fallback to admission with a directed encoding.", "A five-stage flow shows co-occurrence, a prerequisite request, refusal, addition of an explicit cross-reference, and admission."),
        _artifact_record(root, "figure-specification-survival", "figure", specification_figure, [specification_input], "observed", "Union-edge persistence and persistence-gate frontier across the 24-configuration specification surface.", "The left panel compares union-edge persistence across four corpora; the right panel shows the share passing the authored persistence gate as it moves from 0.50 to 1.00."),
        _artifact_record(root, "figure-external-validation", "figure", external_figure, [external_input], "observed", f"Categorical construct-boundary route coverage and Policy {policy_version} consequences across MRPC, PAWS, SNLI, AL-CPL, and TORQUE.", "A five-dataset matrix uses outlined cells, checks with route counts, and N/A labels for inapplicable matched-support, counterevidence, reversal, mention-only, and cross-construct route families; a second panel preserves seventeen deterministic authorization and refusal paths. Table 8 additionally reports separately requested non-paraphrase admission and the remaining cross-construct controls."),
        _artifact_record(root, "mapping-claim-admissibility", "mapping", claim_mapping, [summary_input], "derived", "Observation-to-claim mapping for unordered co-occurrence evidence.", "A flow map admits lexical association, qualifies asymmetric conditional association, and refuses semantic direction when no directional channel is observed."),
        _artifact_record(root, "mapping-empirical-pipeline", "mapping", pipeline_mapping, [summary_input, audit_input], "derived", "Source-to-manuscript empirical artifact and provenance flow.", "A two-row flow diagram links source data through adapters, analysis, validated JSON, generated assets, manifest, and anonymous ACM manuscript."),
        _artifact_record(root, "mapping-themegraph-overview-architecture", "mapping", overview_architecture, [summary_input, benchmark_input, external_input, specification_input], "derived", "Overarching ThemeGraph architecture separating graph computation from certificate-mediated semantic governance across eight certificate-guarded output entry points.", "Two coupled rails show a computational path from corpus provenance to graph structure and an epistemic path from requested semantics and typed evidence through a certificate-required representation monitor. A blocked bypass depicts the maintained boundary across two nonsemantic structural serializers and six semantic representation or export entry points. Admit, qualify, and refuse certificates jointly govern statement, mark, and requested-claim export."),
        _artifact_record(root, "mapping-epistemic-dependency-ladder", "mapping", dependency_ladder, [benchmark_input], "derived", "A dependency sequence of design-specific epistemic gates separating correctness, construct/evidence match, persistence, interpretive validity, and human benefit.", "Five distinct gates form a horizontal dependency sequence showing that computational correctness does not imply construct/evidence match, specification persistence, interpretive validity, or human benefit."),
        _artifact_record(root, "mapping-contract-architecture", "mapping", contract_architecture, [benchmark_input], "derived", "Claim, evidence, and representation architecture of the Epistemic Representation Contract.", "Typed claims and typed evidence enter a versioned policy whose decision governs statement, encoding, export, fallback, witness, and remediation."),
        _artifact_record(root, "figure-contract-properties", "figure", contract_properties_figure, [benchmark_input], "observed", "Adversarial contract-property matrix for seven executable properties.", "Seven rows pair each property with an adversarial perturbation, explicit failure condition, joint-control consequence, and observed result, including directional pair-scope non-transfer."),
        _artifact_record(root, "figure-governance-state-grammars", "figure", governance_triptych, [benchmark_input], "derived", f"Policy {policy_version} design assignments for refusal, reason-specific qualification, and admission; no perceptual effectiveness is inferred.", "Four side-by-side certificate states distinguish refused causality with lexical fallback, prevalence-qualified conditional asymmetry, conflict-qualified interrupted relation with blocked ordinary export, and admitted temporal direction with a solid semantic arrow. These marks are design assignments, not demonstrated perceptual effects."),
        _artifact_record(root, "mapping-governed-inspector-walkthrough", "mapping", governed_walkthrough, [benchmark_input, external_input], "derived", "Governed inspector states for admission, qualification, refusal, fallback, blocked export, counterevidence, and remediation.", "Four rows show lexical-only semantic refusal with fallback, construct-matched admission, negative-counterevidence refusal, and statistical-stability refusal when bootstrap evidence is missing."),
    ]
    if mutation_rows:
        artifacts.extend(
            [
                _artifact_record(root, "table-policy-lint-mutations", "table", [mutation_csv, mutation_family_csv, table_root / "policy_lint_mutations.tex"], [benchmark_input], "observed", f"Family-level manuscript summary and row-level artifact detail for {mutation_count} targeted Policy {policy_version} lint mutations."),
                _artifact_record(root, "figure-policy-lint-mutations", "figure", policy_mutation_figure, [benchmark_input], "observed", "Mutation-by-invariant linter localization matrix with intended targets outlined.", f"A {mutation_count}-by-{mutation_count} matrix shows every triggered lint check for each invalid policy mutation, distinguishing intended detection from co-triggered diagnostics."),
            ]
        )
    if enforcement_rows:
        artifacts.append(
            _artifact_record(root, "table-representation-enforcement", "table", [enforcement_csv, table_root / "representation_enforcement.tex"], [benchmark_input], "observed", f"Five-state certificate-to-representation enforcement under Policy {policy_version}.")
        )
    if ablation_rows:
        artifacts.append(
            _artifact_record(root, "table-architecture-enforcement-ablation", "table", [ablation_csv, table_root / "architecture_enforcement_ablation.tex"], [benchmark_input], "observed", f"Output-Control Reachability Ablation across four generated output-control conditions; unauthorized means not authorized under Policy {policy_version} for the supplied fixture.")
        )
    if necessity_rows:
        artifacts.append(
            _artifact_record(root, "table-contract-field-necessity", "table", [necessity_csv, table_root / "contract_field_necessity.tex"], [benchmark_input], "observed", "One-at-a-time contract-field failure probes and their joint-control consequences.")
        )
    if policy_claim_summary_rows:
        artifacts.append(
            _artifact_record(root, "table-policy-claim-types", "table", [policy_claim_csv, table_root / "policy_claim_types.tex", table_root / "policy_claim_consequences.tex"], [benchmark_input], "derived", f"Policy {policy_version} claim typing and separately rendered representation consequences from one source table.")
        )
    inspector_capture = figure_root / "inspector_policy27_screenshot.png"
    if inspector_capture.exists():
        artifacts.append(
            _artifact_record(
                root,
                "figure-inspector-policy-2-7",
                "figure",
                [inspector_capture],
                [
                    "prototype/index.html",
                    "prototype/styles.css",
                    "prototype/app.js",
                    benchmark_input,
                ],
                "observed-interface-state",
                f"ThemeGraph Inspector showing a Policy {policy_version} certificate governing the visible graph, statement, typed fallback projection, representation authorization, export status, complete reasons, witness, and remediation.",
                f"A browser capture of the ThemeGraph Inspector with analysis controls, a governed graph, and a Policy {policy_version} certificate panel exposing the controlling reason, complete triggered reasons, governed object types, fallback projection provenance, encoding, export status, witness, and remediation.",
            )
        )
    if inspector_composite:
        inspector_crops = [
            figure_root / "inspector_policy27_decision_crop.png",
            figure_root / "inspector_policy27_evidence_crop.png",
            figure_root / "inspector_policy27_encoding_crop.png",
        ]
        artifacts.append(
            _artifact_record(
                root,
                "figure-inspector-policy-2-7-composite",
                "figure",
                inspector_composite + inspector_crops,
                [
                    "prototype/index.html",
                    "prototype/styles.css",
                    "prototype/app.js",
                    benchmark_input,
                ],
                "observed-interface-state",
                f"Readable four-panel Policy {policy_version} inspector composite with source crops.",
                "Panels show the requested claim and decision, typed evidence, fallback projection provenance with witness and remediation, and the certificate-governed graph encoding; the full interface remains a supplementary artifact.",
            )
        )
    if edge_rows:
        artifacts.extend(
            [
                _artifact_record(root, "table-edge-distributions", "table", [edge_csv, table_root / "edge_distributions.tex"], corpus_inputs, "observed", "Retained-edge distribution summaries from per-corpus outputs."),
                _artifact_record(root, "figure-edge-distributions", "figure", edge_figure, corpus_inputs, "observed", "Median and interquartile range of confidence, support, and lift among retained edges.", "Three interval plots compare retained-edge confidence, support, and lift distributions across five corpora."),
            ]
        )

    empirical_results = output_root / "EMPIRICAL_RESULTS.md"
    _write_empirical_results(
        empirical_results,
        summary,
        audit,
        external,
        specification,
        corpus_rows,
        threshold_rows,
    )
    artifacts.append(
        _artifact_record(root, "report-empirical-results", "report", [empirical_results], [summary_input, audit_input, external_input, specification_input], "observed", "Measured results and explicit claim boundaries for manuscript development.")
    )

    inventory_path = output_root / "ARTIFACT_INVENTORY.md"
    artifacts.append(
        _artifact_record(root, "report-artifact-inventory", "report", [inventory_path], [summary_input, audit_input], "derived", "Inventory, captions, and alt text for generated publication artifacts.")
    )

    readme_path = output_root / "README.md"
    readme_path.write_text(
        "# Publication Artifacts\n\n"
        "Generate from the workspace root with:\n\n"
        "```powershell\n"
        ".\\.venv\\Scripts\\python.exe scripts/build_publication_artifacts.py\n"
        "```\n\n"
        "The first author reports collecting the combined Glassdoor and SimplyHired "
        "dataset in June 2023. Public release under CC BY 4.0 is planned, but no public "
        "deposit URL is recorded yet. Raw job text is excluded from these artifacts. "
        "See `manifest.json` for source and output hashes.\n",
        encoding="ascii",
    )
    artifacts.append(
        _artifact_record(root, "readme-publication-artifacts", "documentation", [readme_path], [summary_input, audit_input], "derived", "Rebuild command and data-use boundary.")
    )
    _write_inventory(inventory_path, artifacts)

    direct_inputs = [
        summary_path,
        audit_path,
        benchmark_path,
        specification_path,
        external_path,
        *corpus_result_paths.values(),
    ]
    for candidate in [
        root / "glassdoor_simplyhired_jobs_data.xlsx",
        root / "glassdoor_simplyhired_jobs_data.metadata.json",
        root / "data" / "external" / "db_30_3_text.zip",
        root / "scripts" / "run_research_evaluation.py",
        root / "scripts" / "build_publication_artifacts.py",
        root / "scripts" / "validate_publication_artifacts.py",
        root / "scripts" / "run_external_validation.py",
        root / "src" / "themegraph" / "publication.py",
        root / "src" / "themegraph" / "external_validation.py",
    ]:
        if candidate.exists():
            direct_inputs.append(candidate)
    input_records = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in direct_inputs
    ]
    output_paths = [
        root / relative_path
        for artifact in artifacts
        for relative_path in artifact["files"]
    ]
    manifest = {
        "schema_version": "1.1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "generator": "themegraph.publication.build_publication_artifacts",
        "environment": summary.get("environment", {}),
        "data_boundary": {
            "job_ads_provenance": audit["provenance_status"],
            "job_ads_redistribution": audit["redistribution_status"],
            "intended_release_license": audit["dataset_metadata"][
                "intended_public_release_license"
            ],
            "public_release_status": audit["dataset_metadata"]["public_release_status"],
            "platform_permission_documented": audit["dataset_metadata"][
                "platform_permission_documented"
            ],
            "sampling_frame_status": audit["dataset_metadata"]["sampling_frame_status"],
            "per_row_platform_available": audit["source_platform_column_present"],
            "raw_job_ad_text_included": False,
            "raw_external_sentence_text_included": False,
            "labor_market_inference_supported": False,
        },
        "inputs": input_records,
        "artifacts": artifacts,
        "outputs": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in output_paths
        ],
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return manifest