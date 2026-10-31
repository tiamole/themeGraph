"""Build manuscript figures restricted to the four corpora the paper claims.

``themegraph.publication`` computes structural, performance, and edge-distribution
figures across six corpora, including the Glassdoor/SimplyHired job-ad workbook. The
manuscript's Ethics, Limitations, and Scope section deliberately keeps that workbook
"outside the paper's claims" because its source, sampling frame, and redistribution
license are unresolved (see ``ACM_CHI_2027_RESEARCH_REPORT.md``). This script re-renders
the same measured statistics restricted to the four corpora the paper does claim
(synthetic, O*NET, ACM text, Python standard library) so the manuscript's structural,
performance, and distribution figures stay consistent with its own stated evidentiary
scope. It also derives two figures that are not produced by the existing pipeline:

1. Directional asymmetry magnitude: for every retained edge, the forward confidence
   that passed the admission threshold is compared with the confidence its reversed
   orientation would have received, computed from the same serialized confidence,
   support, and lift fields via Equations 1 and 2 of the manuscript. This replaces the
   paper's algebraic identity (Equation 3) with its observed magnitude on real corpora.
2. Evidence retention completeness: the serialized evidence list on each edge is capped
   at ``evidence_limit`` excerpts (3 in all four corpora); this script reports what
   share of retained edges have more supporting documents than the capped list can show.

All inputs are the existing, already-validated JSON artifacts in ``results/``; no new
corpus analysis or text extraction is performed.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from themegraph.publication import (
    PALETTE,
    _corpus_label,
    _corpus_structure_figure,
    _edge_distribution_figure,
    _panel_title,
    _percentile,
    _performance_figure,
    _quiet_grid,
    _save_figure,
    _threshold_sensitivity_figure,
    _write_latex_table,
    corpus_overview_rows,
    edge_distribution_rows,
    threshold_sensitivity_rows,
)

CORE_CORPORA = ("synthetic", "onet_500", "acmart", "python_stdlib_100")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _filter_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["corpus"] in CORE_CORPORA]


def _directional_asymmetry_rows(
    corpus_payloads: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive the implied reverse-orientation confidence for every retained edge.

    For a retained edge a -> b the extractor records support = n(a, b), confidence =
    n(a, b) / n(a), and lift = n(a, b) * N / (n(a) * n(b)) (``relations.py``). Source
    prevalence n(a) = support / confidence and target prevalence n(b) = N * confidence
    / lift follow directly from those two definitions, so the reverse confidence
    conf(b -> a) = n(a, b) / n(b) = support / n(b) is fully determined by fields already
    serialized on the forward edge. This is an exact algebraic recomputation, not an
    independent measurement; it reports the real observed magnitude of Equation 3 on
    each corpus's retained edges rather than re-deriving the identity itself.
    """
    rows = []
    for name, payload in corpus_payloads.items():
        edges = payload.get("edges", [])
        unit_count = payload["unit_count"]
        forward = []
        reverse = []
        for edge in edges:
            confidence = float(edge["confidence"])
            support = float(edge["support"])
            lift = float(edge["lift"])
            if lift <= 0 or confidence <= 0:
                continue
            target_prevalence = confidence / lift
            implied_target_units = target_prevalence * unit_count
            if implied_target_units <= 0:
                continue
            implied_reverse_confidence = min(support / implied_target_units, 1.0)
            forward.append(confidence)
            reverse.append(implied_reverse_confidence)
        if not forward:
            continue
        rows.append(
            {
                "corpus": name,
                "edge_count": len(forward),
                "forward_p25": _percentile(forward, 0.25),
                "forward_median": median(forward),
                "forward_p75": _percentile(forward, 0.75),
                "reverse_p25": _percentile(reverse, 0.25),
                "reverse_median": median(reverse),
                "reverse_p75": _percentile(reverse, 0.75),
            }
        )
    return rows


def _evidence_retention_rows(
    corpus_payloads: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Measure how much corroborating documentary support is shown per edge.

    Each edge's ``evidence`` list is capped at the configured ``evidence_limit``
    (3 for every corpus analyzed here); ``document_support`` records the true number
    of distinct documents containing the pair. An edge is truncated when
    document_support exceeds evidence_limit, meaning the inspector and export surface
    a strict subset of the documents that actually support the retained edge.
    """
    rows = []
    for name, payload in corpus_payloads.items():
        edges = payload.get("edges", [])
        if not edges:
            continue
        evidence_limit = payload["configuration"]["relation_extractor"]["evidence_limit"]
        truncated = 0
        retention_ratios = []
        document_supports = []
        for edge in edges:
            shown = len(edge.get("evidence", []))
            document_support = int(edge["document_support"])
            document_supports.append(document_support)
            if document_support > evidence_limit:
                truncated += 1
                retention_ratios.append(shown / document_support)
            else:
                retention_ratios.append(1.0)
        rows.append(
            {
                "corpus": name,
                "edge_count": len(edges),
                "evidence_limit": evidence_limit,
                "truncated_edges": truncated,
                "truncated_rate": truncated / len(edges),
                "median_document_support": int(round(median(document_supports))),
                "median_retention_ratio_when_truncated": (
                    median([r for r in retention_ratios if r < 1.0]) if truncated else 1.0
                ),
            }
        )
    return rows


def _directional_asymmetry_figure(rows: list[dict[str, Any]], output_stem: Path) -> list[Path]:
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    fig = Figure(figsize=(7.1, 2.35), constrained_layout=True)
    axis = fig.subplots()
    labels = [_corpus_label(row["corpus"]) for row in rows]
    positions = list(range(len(rows)))
    offset = 0.17
    for position, row in zip(positions, rows, strict=True):
        top = position - offset
        axis.hlines(top, row["forward_p25"], row["forward_p75"], color=PALETTE["vermilion"], linewidth=2.2)
        axis.plot(row["forward_median"], top, "o", color=PALETTE["vermilion"], markersize=4.5, markeredgecolor="white", markeredgewidth=0.6, zorder=3)
        bottom = position + offset
        axis.hlines(bottom, row["reverse_p25"], row["reverse_p75"], color=PALETTE["blue"], linewidth=2.2)
        axis.plot(row["reverse_median"], bottom, "o", color=PALETTE["blue"], markersize=4.5, markeredgecolor="white", markeredgewidth=0.6, zorder=3)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlim(0, 1.02)
    from matplotlib.ticker import PercentFormatter

    axis.xaxis.set_major_formatter(PercentFormatter(1.0))
    axis.set_xlabel("Conditional confidence, median and interquartile range")
    axis.axvline(0.65, color=PALETTE["gray"], linewidth=0.8, linestyle=(0, (3, 2)))
    axis.text(
        0.98,
        0.96,
        "admission threshold 0.65",
        fontsize=6.5,
        color=PALETTE["gray"],
        ha="right",
        va="top",
        transform=axis.transAxes,
    )
    _panel_title(axis, "A", "Retained edges: admitted direction versus its reversal")
    _quiet_grid(axis)
    handles = [
        Line2D([], [], marker="o", linestyle="", markerfacecolor=PALETTE["vermilion"], markeredgecolor="white", label="Admitted orientation conf(a to b)"),
        Line2D([], [], marker="o", linestyle="", markerfacecolor=PALETTE["blue"], markeredgecolor="white", label="Implied reverse conf(b to a)"),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=2, handletextpad=0.4, columnspacing=1.0)
    return _save_figure(fig, output_stem)


def _evidence_retention_figure(rows: list[dict[str, Any]], output_stem: Path) -> list[Path]:
    from matplotlib.figure import Figure
    from matplotlib.ticker import PercentFormatter

    fig = Figure(figsize=(7.1, 2.1), constrained_layout=True)
    axis = fig.subplots()
    labels = [_corpus_label(row["corpus"]) for row in rows]
    positions = list(range(len(rows)))
    rates = [row["truncated_rate"] for row in rows]
    for position, rate in zip(positions, rates, strict=True):
        axis.hlines(position, 0, rate, color=PALETTE["gold"], linewidth=2.2)
        axis.scatter(rate, position, s=42, color=PALETTE["gold"], edgecolor="white", linewidth=0.7, zorder=3)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlim(0, 1.0)
    axis.xaxis.set_major_formatter(PercentFormatter(1.0))
    axis.set_xlabel("Retained edges with more supporting documents than shown excerpts")
    _panel_title(axis, "A", "Evidence-retention completeness")
    _quiet_grid(axis)
    for position, row in zip(positions, rows, strict=True):
        axis.text(
            min(row["truncated_rate"] + 0.02, 0.93),
            position,
            f"{row['truncated_rate']:.1%}  |  cap {row['evidence_limit']} of median {row['median_document_support']:.0f} documents",
            va="center",
            color=PALETTE["ink"],
            fontsize=6.8,
            fontweight="bold",
        )
    return _save_figure(fig, output_stem)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = _read_json(root / "results" / "research_evaluation_summary.json")
    figure_root = root / "artifacts" / "figures"
    table_root = root / "artifacts" / "tables"

    corpus_rows = _filter_rows(corpus_overview_rows(summary))
    threshold_rows = _filter_rows(threshold_sensitivity_rows(summary))

    corpus_payloads = {}
    for name in CORE_CORPORA:
        path = root / "results" / "evaluation_corpora" / f"{name}.json"
        if path.exists():
            corpus_payloads[name] = _read_json(path)
    edge_rows = edge_distribution_rows(corpus_payloads)
    asymmetry_rows = _directional_asymmetry_rows(corpus_payloads)
    retention_rows = _evidence_retention_rows(corpus_payloads)

    _corpus_structure_figure(corpus_rows, figure_root / "cross_corpus_structure_core")
    _performance_figure(corpus_rows, figure_root / "measured_performance_core")
    _edge_distribution_figure(edge_rows, figure_root / "edge_distributions_core")
    _threshold_sensitivity_figure(threshold_rows, figure_root / "threshold_sensitivity_core")
    _directional_asymmetry_figure(asymmetry_rows, figure_root / "directional_asymmetry")
    _evidence_retention_figure(retention_rows, figure_root / "evidence_retention")

    _write_latex_table(
        table_root / "directional_asymmetry.tex",
        asymmetry_rows,
        [
            ("corpus", "Corpus", "l"),
            ("edge_count", "Retained edges", "r"),
            ("forward_median", "Admitted conf. median", "r"),
            ("reverse_median", "Implied reverse conf. median", "r"),
        ],
        "Admitted-orientation confidence against the implied reverse-orientation confidence derived from the same serialized support, confidence, and lift fields.",
        "tab:directional-asymmetry",
    )
    _write_latex_table(
        table_root / "evidence_retention.tex",
        retention_rows,
        [
            ("corpus", "Corpus", "l"),
            ("edge_count", "Retained edges", "r"),
            ("truncated_rate", "Share truncated", "r"),
            ("median_document_support", "Median supporting documents", "r"),
        ],
        "Share of retained edges whose supporting-document count exceeds the serialized evidence cap of three excerpts.",
        "tab:evidence-retention",
    )

    print("Core-corpus figures and tables written.")
    for row in asymmetry_rows:
        print(
            f"  {row['corpus']}: n={row['edge_count']} forward_median={row['forward_median']:.3f} "
            f"reverse_median={row['reverse_median']:.3f}"
        )
    for row in retention_rows:
        print(
            f"  {row['corpus']}: truncated_rate={row['truncated_rate']:.3f} "
            f"median_document_support={row['median_document_support']:.1f}"
        )


if __name__ == "__main__":
    main()
