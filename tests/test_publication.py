from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.validate_publication_artifacts import (
    _validate_complete_mediation,
    _validate_manuscript_claim_identifiers,
)
from themegraph.publication import (
    build_publication_artifacts,
    external_validation_rows,
    threshold_table_rows,
)
from themegraph.representation import COMPLETE_MEDIATION_ENTRY_POINTS


def test_manuscript_claim_identifier_rejects_misspelling(tmp_path: Path) -> None:
    manuscript = tmp_path / "manuscript" / "themegraph_chi_2027.tex"
    manuscript.parent.mkdir()
    manuscript.write_text(
        r"We exercised this protocol by adding \texttt{concept-eqivalence}.",
        encoding="utf-8",
    )
    benchmark = {"policy": {"claims": [{"claim": "concept-equivalence"}]}}

    with pytest.raises(ValueError, match="undeclared policy-extension claim ID"):
        _validate_manuscript_claim_identifiers(tmp_path, benchmark)

    manuscript.write_text(
        r"We exercised this protocol by adding \texttt{concept-equivalence}.",
        encoding="utf-8",
    )
    _validate_manuscript_claim_identifiers(tmp_path, benchmark)


def _write_complete_mediation_fixture(root: Path) -> dict[str, object]:
    sources = {
        root / "src" / "themegraph" / "pipeline.py": """
# certificate-guarded-output-entry-point: analysis-result serialization; guard=validate_certificate_collection
def export_result():
    validate_certificate_collection()
""",
        root / "src" / "themegraph" / "cli.py": """
# certificate-guarded-output-entry-point: CLI structural export; guard=export_result
def main():
    export_result()
""",
        root / "src" / "themegraph" / "representation.py": """
# certificate-guarded-output-entry-point: governed-representation API; guard=certificate_for_claim
def governed_representation():
    certificate_for_claim()

# certificate-guarded-output-entry-point: requested-claim export API; guard=governed_representation
def export_requested_claim():
    governed_representation()
""",
        root / "src" / "themegraph" / "benchmark.py": """
# certificate-guarded-output-entry-point: publication representation enforcement; guard=validate_certificate_payload
def representation_enforcement_benchmark():
    validate_certificate_payload()
""",
        root / "prototype" / "app.js": """
// certificate-guarded-output-entry-point: inspector statement rendering; guard=requireCertificate
function renderCertificate() { requireCertificate(); }
// certificate-guarded-output-entry-point: inspector graph-mark rendering; guard=requireCertificate
function renderGraph() { requireCertificate(); }
// certificate-guarded-output-entry-point: inspector requested-claim export; guard=requireCertificate
elements["export-button"].addEventListener("click", () => { requireCertificate(); });
""",
    }
    for path, source in sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return {
        "complete_mediation": {
            "entry_points": list(COMPLETE_MEDIATION_ENTRY_POINTS),
            "entry_point_count": len(COMPLETE_MEDIATION_ENTRY_POINTS),
            "all_certificate_required": True,
        }
    }


def test_complete_mediation_inventory_rejects_removed_guard(tmp_path: Path) -> None:
    benchmark = _write_complete_mediation_fixture(tmp_path)

    _validate_complete_mediation(tmp_path, benchmark)
    unguarded_path = tmp_path / "src" / "themegraph" / "benchmark.py"
    unguarded_path.write_text(
        "# certificate-guarded-output-entry-point: publication representation enforcement; "
        "guard=validate_certificate_payload\n"
        "def representation_enforcement_benchmark():\n    return {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Certificate mediation is absent"):
        _validate_complete_mediation(tmp_path, benchmark)


def test_complete_mediation_inventory_discovers_unlisted_emitter(tmp_path: Path) -> None:
    benchmark = _write_complete_mediation_fixture(tmp_path)
    bypass = tmp_path / "src" / "themegraph" / "bypass.py"
    bypass.write_text(
        "def emit_semantic_output():\n    return {'allowed_statement': 'bypass'}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Uninventoried semantic-output candidate"):
        _validate_complete_mediation(tmp_path, benchmark)


def test_publication_artifacts_trace_values_and_formats(tmp_path: Path) -> None:
    root = tmp_path
    results = root / "results"
    results.mkdir()
    (results / "research_evaluation_summary.json").write_text(
        json.dumps(
            {
                "corpora": {
                    "measured": {
                        "default": {
                            "structural": {
                                "documents": 10,
                                "units": 20,
                                "nodes": 5,
                                "edges": 4,
                                "scc_count": 3,
                                "largest_scc": 2,
                                "singleton_rate": 2 / 3,
                                "asymmetric_edge_rate": 0.5,
                            },
                            "performance": {
                                "core_wall_seconds": 0.25,
                                "peak_python_allocation_bytes": 1048576,
                            },
                            },
                            "threshold_sweep": [
                                {
                                    "min_confidence": 0.5,
                                    "min_lift": 1.0,
                                    "edges": 4,
                                    "scc_count": 3,
                                    "largest_scc": 2,
                                    "singleton_rate": 2 / 3,
                                    "asymmetric_edge_rate": 0.5,
                                }
                            ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (results / "glassdoor_simplyhired_jobs_audit.json").write_text(
        json.dumps(
            {
                "row_count": 100,
                "null_counts": {"Description": 1},
                "null_rates": {"Description": 0.01},
                "exact_duplicate_row_instances": 10,
                "exact_duplicate_description_instances": 12,
                "source_platform_column_present": False,
                "provenance_status": "author_attested_file_supported_in_part",
                "redistribution_status": "planned_not_yet_verified_by_public_deposit",
                "dataset_metadata": {
                    "intended_public_release_license": "CC BY 4.0",
                    "public_release_status": "planned",
                    "platform_permission_documented": False,
                    "sampling_frame_status": "not_documented",
                },
            }
        ),
        encoding="utf-8",
    )
    (results / "claim_admissibility_benchmark.json").write_text(
        json.dumps(
            {
                "policy": {"policy_version": "2.2.0", "claims": []},
                "policy_lint": {
                    "checks": {"all_claims_declared": True},
                },
                "claim_decisions": {
                        "policy_conformance_rate": 1.0,
                        "decision_disagreement_rate": 0.0,
                        "fallback_disagreement_rate": 0.0,
                    "cases": [
                        {
                            "case_id": "fixture",
                            "expected_decision": "ADMIT",
                            "certificate": {
                                "claim_type": "lexical-association",
                                "decision": "ADMIT",
                                "allowed_encoding": "undirected-link",
                                "fallback_claim": None,
                            },
                        }
                    ],
                },
                "contract_properties": {
                    "checks": {"construct_matching": True},
                    "falsification_matrix": [
                        {
                            "property": "construct matching",
                            "perturbation": "Use mismatched evidence",
                            "failure_condition": "Mismatched claim is admitted",
                        }
                    ],
                },
                "directed_reference_transition": {
                    "reference_edges": [
                        ["alpha", "beta"],
                        ["beta", "gamma"],
                        ["gamma", "delta"],
                        ["delta", "epsilon"],
                    ],
                    "initial_refusal_rate": 1.0,
                    "augmented_admission_rate": 1.0,
                    "edge_precision": 1.0,
                    "edge_recall": 1.0,
                },
                "controlled_duplication_stress": {
                    "benchmark_type": "generated fixture",
                    "license": "generated",
                    "base_source_count": 2,
                    "row_count": 4,
                    "unique_record_count": 2,
                    "duplicate_rows_beyond_first": 2,
                    "duplicate_rate": 0.5,
                    "naive_support_inflation_factor": 2.0,
                    "interpretation": "Copies do not add independent sources.",
                },
            }
        ),
        encoding="utf-8",
    )
    (results / "specification_surface.json").write_text(
        json.dumps(
            {
                "corpora": {
                    "measured": {
                            "configuration_count": 24,
                            "bounded_interaction_configuration_count": 6,
                        "baseline_edge_count": 2,
                        "union_edge_count": 3,
                        "edge_survival": {
                            "a->b": 1.0,
                            "b->a": 0.75,
                            "b->c": 0.25,
                        },
                        "default_edge_survival": {"a->b": 1.0, "b->a": 0.75},
                            "edge_set_geometry": {
                                "union_count": 3,
                                "intersection_count": 1,
                                "emergent_count": 1,
                            },
                        "survival_summary": {
                            "edge_minimum": 0.25,
                            "edge_mean": 2 / 3,
                            "default_edge_mean": 0.875,
                                "component_overlap_mean": 0.8,
                        },
                            "gate_frontier": [
                                {
                                    "survival_gate": 0.5,
                                    "admitted_union_edges": 2,
                                    "qualified_union_edges": 1,
                                },
                                {
                                    "survival_gate": 0.8,
                                    "admitted_union_edges": 1,
                                    "qualified_union_edges": 2,
                                },
                                {
                                    "survival_gate": 1.0,
                                    "admitted_union_edges": 1,
                                    "qualified_union_edges": 2,
                                },
                            ],
                        "certificate_consequences": {
                            "admitted_union_edges": 1,
                            "qualified_union_edges": 2,
                            "admitted_default_edges": 1,
                            "qualified_default_edges": 1,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (results / "external_validation.json").write_text(
        json.dumps(
            {
                "datasets": {
                    "mrpc": {
                        "record_count": 3,
                        "label_counts": {"paraphrase": 2, "non_paraphrase": 1},
                        "lexical_overlap": {
                            "mean_jaccard": 0.5,
                            "high_overlap_non_paraphrase_count": 1,
                            "by_label": {
                                "paraphrase": {
                                    "p25": 0.4,
                                    "median": 0.5,
                                    "p75": 0.6,
                                },
                                "non_paraphrase": {
                                    "p25": 0.6,
                                    "median": 0.7,
                                    "p75": 0.8,
                                },
                            },
                        },
                        "contract_outcomes": {
                            "positive_annotation_admission_rate": 1.0,
                            "negative_counterevidence_refusal_rate": 1.0,
                            "negative_claim_admission_rate": 1.0,
                            "cross_construct_admission_rate": 0.0,
                        },
                        "contract_routes": [
                            {
                                "evidence_condition": "matched paraphrase annotation",
                                "outcome_key": "positive_annotation_admission_rate",
                                "requested_claim": "sentential-paraphrase-equivalence",
                                "expected_consequence": "ADMIT",
                                "failure_or_authorization_path": "authorized",
                            }
                        ],
                    },
                    "paws": {
                        "record_count": 4,
                        "label_counts": {"paraphrase": 2, "non_paraphrase": 2},
                        "lexical_overlap": {
                            "mean_jaccard": 0.9,
                            "high_overlap_non_paraphrase_count": 2,
                            "by_label": {
                                "paraphrase": {
                                    "p25": 0.8,
                                    "median": 0.9,
                                    "p75": 1.0,
                                },
                                "non_paraphrase": {
                                    "p25": 0.8,
                                    "median": 0.9,
                                    "p75": 1.0,
                                },
                            },
                        },
                        "contract_outcomes": {
                            "positive_annotation_admission_rate": 1.0,
                            "negative_counterevidence_refusal_rate": 1.0,
                            "cross_construct_admission_rate": 0.0,
                        },
                        "contract_routes": [
                            {
                                "evidence_condition": "matched non-paraphrase annotation",
                                "outcome_key": "negative_claim_admission_rate",
                                "requested_claim": "sentential-non-paraphrase",
                                "expected_consequence": "ADMIT",
                                "failure_or_authorization_path": "authorized",
                            }
                        ],
                    },
                    "snli": {
                        "record_count": 6,
                        "label_counts": {
                            "entailment": 2,
                            "neutral": 2,
                            "contradiction": 2,
                        },
                        "lexical_overlap": {
                            "mean_jaccard": 0.25,
                            "high_overlap_non_entailment_count": 1,
                            "by_label": {
                                "entailment": {
                                    "p25": 0.2,
                                    "median": 0.3,
                                    "p75": 0.4,
                                },
                                "neutral": {
                                    "p25": 0.1,
                                    "median": 0.2,
                                    "p75": 0.3,
                                },
                                "contradiction": {
                                    "p25": 0.1,
                                    "median": 0.2,
                                    "p75": 0.3,
                                },
                            },
                        },
                        "contract_outcomes": {
                            "directional_annotation_admission_rate": 1.0,
                            "neutral_insufficient_support_refusal_rate": 1.0,
                            "contradiction_counterevidence_refusal_rate": 1.0,
                            "annotation_nontransfer_refusal_rate": 1.0,
                            "cross_construct_admission_rate": 0.0,
                        },
                        "contract_routes": [
                            {
                                "evidence_condition": "matched entailment annotation",
                                "outcome_key": "directional_annotation_admission_rate",
                                "requested_claim": "textual-entailment",
                                "expected_consequence": "ADMIT",
                                "failure_or_authorization_path": "authorized",
                            }
                        ],
                    },
                    "al_cpl": {
                        "record_count": 5,
                        "label_counts": {
                            "prerequisite": 2,
                            "non_prerequisite": 3,
                        },
                        "contract_outcomes": {
                            "matched_annotation_admission_rate": 1.0,
                            "negative_counterevidence_refusal_rate": 1.0,
                            "reverse_nontransfer_refusal_rate": 1.0,
                            "cross_construct_admission_rate": 0.0,
                        },
                        "contract_routes": [
                            {
                                "evidence_condition": "matched prerequisite annotation",
                                "outcome_key": "matched_annotation_admission_rate",
                                "requested_claim": "concept-prerequisite",
                                "expected_consequence": "ADMIT",
                                "failure_or_authorization_path": "authorized",
                            }
                        ],
                    },
                    "torque": {
                        "record_count": 4,
                        "label_counts": {
                            "usable_relation_annotations": 4,
                            "answerless_directional_questions": 1,
                        },
                        "contract_outcomes": {
                            "matched_annotation_admission_rate": 1.0,
                            "mention_order_refusal_rate": 1.0,
                            "reverse_nontransfer_refusal_rate": 1.0,
                            "cross_construct_admission_rate": 0.0,
                        },
                        "contract_routes": [
                            {
                                "evidence_condition": "mention order only",
                                "outcome_key": "mention_order_refusal_rate",
                                "requested_claim": "event-temporal-precedence",
                                "expected_consequence": "REFUSE",
                                "failure_or_authorization_path": "mention-order-insufficient",
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    manifest = build_publication_artifacts(root)

    with (root / "artifacts" / "tables" / "job_ads_quality.csv").open(
        encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert [float(row["rate"]) for row in rows] == [0.01, 0.1, 0.12]
    assert {path.suffix for path in (root / "artifacts" / "figures").iterdir()} == {
        ".pdf",
        ".png",
        ".svg",
    }
    assert all(record["sha256"] for record in manifest["outputs"])


def test_threshold_table_compacts_only_lift_invariant_rows() -> None:
    rows = [
        {
            "corpus": "fixture",
            "min_confidence": 0.65,
            "min_lift": lift,
            "edges": 3,
            "scc_count": 2,
            "largest_scc": 2,
        }
        for lift in (1.0, 1.05, 1.25)
    ]

    assert threshold_table_rows(rows) == [
        {
            "corpus": "fixture",
            "min_confidence": 0.65,
            "lift_range": "1.00 to 1.25",
            "edges": 3,
            "scc_count": 2,
            "largest_scc": 2,
        }
    ]

    rows[1]["edges"] = 4
    assert [row["lift_range"] for row in threshold_table_rows(rows)] == [
        "1.00",
        "1.05",
        "1.25",
    ]


def test_external_rows_include_distinct_claim_and_mention_order_routes() -> None:
    rows = external_validation_rows(
        {
            "datasets": {
                "mrpc": {
                    "contract_routes": [
                        {
                            "evidence_condition": "matched non-paraphrase annotation",
                            "outcome_key": "negative_claim_admission_rate",
                            "requested_claim": "sentential-non-paraphrase",
                            "expected_consequence": "ADMIT",
                            "failure_or_authorization_path": "authorized",
                        }
                    ],
                    "contract_outcomes": {
                        "negative_claim_admission_rate": 1.0,
                    }
                },
                "al_cpl": {
                    "contract_routes": [
                        {
                            "evidence_condition": "mention order only",
                            "outcome_key": "mention_order_refusal_rate",
                            "requested_claim": "concept-prerequisite",
                            "expected_consequence": "REFUSE",
                            "failure_or_authorization_path": "evidence-channel-absent",
                        }
                    ],
                    "contract_outcomes": {
                        "mention_order_refusal_rate": 1.0,
                    }
                },
                "torque": {
                    "contract_routes": [
                        {
                            "evidence_condition": "mention order only",
                            "outcome_key": "mention_order_refusal_rate",
                            "requested_claim": "event-temporal-precedence",
                            "expected_consequence": "REFUSE",
                            "failure_or_authorization_path": "mention-order-insufficient",
                        }
                    ],
                    "contract_outcomes": {
                        "mention_order_refusal_rate": 1.0,
                    }
                },
            }
        }
    )

    routes = {
        (row["dataset"], row["evidence_condition"]): (
            row["requested_claim"],
            row["observed_consequence"],
            row["failure_or_authorization_path"],
        )
        for row in rows
    }
    assert routes[("MRPC", "matched non-paraphrase annotation")] == (
        "sentential-non-paraphrase",
        "ADMIT",
        "authorized",
    )
    assert routes[("AL-CPL", "mention order only")] == (
        "concept-prerequisite",
        "REFUSE",
        "evidence-channel-absent",
    )
    assert routes[("TORQUE", "mention order only")] == (
        "event-temporal-precedence",
        "REFUSE",
        "mention-order-insufficient",
    )