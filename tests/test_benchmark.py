from themegraph.benchmark import complete_benchmark


def test_controlled_benchmark_has_no_policy_decision_errors() -> None:
    result = complete_benchmark()
    decisions = result["claim_decisions"]

    assert decisions["case_count"] == 10
    assert decisions["policy_conformance_rate"] == 1.0
    assert decisions["decision_disagreement_rate"] == 0.0
    assert decisions["fallback_disagreement_rate"] == 0.0
    assert decisions["remediation_coverage"] == 1.0

    cases = {case["case_id"]: case["certificate"] for case in decisions["cases"]}
    assert cases["conflicting-annotations"]["triggered_reasons"] == [
        "conflict-present"
    ]
    assert cases["conflicting-annotations"]["decision_reason"] == "conflict-present"
    assert cases["conflicting-annotations"]["witness"] == (
        (
            "Construct-matched conflict: support: A precedes B; "
            "counterevidence: B precedes A."
        ),
    )
    assert cases["duplicated-evidence"]["triggered_reasons"] == [
        "uncertainty-inadequate",
        "dependence-inadequate",
    ]
    assert cases["duplicated-evidence"]["decision_reason"] == "uncertainty-inadequate"
    assert all(
        case["certificate"]["triggered_reasons"]
        for case in decisions["cases"]
        if case["certificate"]["decision"] != "ADMIT"
    )


def test_formal_contract_properties_pass() -> None:
    properties = complete_benchmark()["contract_properties"]

    assert properties["check_count"] == 7
    assert properties["all_passed"] is True
    no_laundering = next(
        row
        for row in properties["falsification_matrix"]
        if row["property"] == "no validity laundering"
    )
    assert no_laundering["perturbation"] == (
        "Set specification persistence and uncertainty adequacy without causal evidence"
    )


def test_policy_version_change_is_traceable_and_behavioral() -> None:
    contestability = complete_benchmark()["policy_contestability"]

    assert contestability["decision_changed"] is True
    assert contestability["version_traceable"] is True
    assert [
        certificate["decision"] for certificate in contestability["certificates"]
    ] == ["ADMIT", "REFUSE"]


def test_observational_equivalence_refuses_opposing_latent_directions() -> None:
    result = complete_benchmark()["observational_equivalence"]

    assert result["unordered_signatures_equal"] is True
    assert result["both_refused"] is True


def test_explicit_reference_upgrades_refusal_to_admission() -> None:
    result = complete_benchmark()["directed_reference_transition"]

    assert result["initial_refusal_rate"] == 1.0
    assert result["augmented_admission_rate"] == 1.0
    assert result["edge_precision"] == 1.0
    assert result["edge_recall"] == 1.0


def test_active_policy_passes_structural_and_behavioral_lint() -> None:
    result = complete_benchmark()["policy_lint"]

    assert result["check_count"] >= 10
    assert result["all_passed"] is True
    assert result["issues"] == []


def test_policy_linter_detects_all_targeted_mutations() -> None:
    result = complete_benchmark()["policy_lint_mutations"]

    assert result["mutation_count"] == 21
    assert result["detected_count"] == 21
    assert result["detection_rate"] == 1.0
    assert result["all_intended_mutations_detected"] is True
    assert len(result["check_names"]) == 21
    assert all(
        len(mutation["detection_vector"]) == 21
        for mutation in result["mutations"]
    )


def test_contract_field_necessity_exposes_each_invalid_behavior() -> None:
    result = complete_benchmark()["contract_field_necessity"]

    assert result["distinction_count"] == 7
    assert result["all_failures_detected"] is True
    assert {row["distinction"] for row in result["rows"]} == {
        "governed-object type",
        "scope and orientation",
        "evidence polarity",
        "projection provenance",
        "fallback projection",
        "export authorization",
        "required adjudication",
    }
    assert all(row["invalid_behavior_enabled"] for row in result["rows"])
    assert all(row["contribution_consequence"] for row in result["rows"])


def test_controlled_duplication_separates_rows_from_sources() -> None:
    result = complete_benchmark()["controlled_duplication_stress"]

    assert result["base_source_count"] == 12
    assert result["row_count"] == 48
    assert result["duplicate_rows_beyond_first"] == 36
    assert result["naive_support_inflation_factor"] == 4.0


def test_representation_enforcement_matrix_covers_all_policy_states() -> None:
    result = complete_benchmark()["representation_enforcement"]

    assert result["state_count"] == 5
    assert result["all_conform"] is True
    assert {row["state"] for row in result["states"]} == {
        "admit",
        "prevalence-qualify",
        "conflict-qualify",
        "refuse-with-fallback",
        "refuse-without-fallback",
    }
    assert {
        row["state"]: row["permitted_statement"] for row in result["states"]
    } == {
        "admit": "semantic claim",
        "prevalence-qualify": "qualified statistic",
        "conflict-qualify": "contested claim",
        "refuse-with-fallback": "fallback statement",
        "refuse-without-fallback": "refusal explanation",
    }
    assert all(all(row["checks"].values()) for row in result["states"])


def test_architecture_ablation_blocks_output_leakage_and_preserves_fallback() -> None:
    benchmark = complete_benchmark()
    result = benchmark["architecture_enforcement_ablation"]

    assert result["benchmark_type"] == "output-control reachability ablation"
    assert result["architecture_count"] == 4
    assert result["fixture_count"] == 3
    assert result["output_path_count"] == 8
    assert benchmark["complete_mediation"]["entry_point_count"] == 8
    assert benchmark["complete_mediation"]["structural_entry_point_count"] == 2
    assert benchmark["complete_mediation"]["semantic_entry_point_count"] == 6
    assert result["enforcement_blocks_all_unauthorized_outputs"] is True
    assert result["enforcement_preserves_lawful_fallback"] is True
    rows = {row["architecture"]: row for row in result["architectures"]}
    for baseline in (
        "graph-pipeline-only",
        "warning-layer",
        "certificate-visible-non-enforcing",
    ):
        assert rows[baseline]["unauthorized_statements_emitted"] == 3
        assert rows[baseline]["unauthorized_semantic_marks_emitted"] == 3
        assert rows[baseline]["unauthorized_requested_exports_emitted"] == 3
        assert rows[baseline]["lawful_fallbacks_preserved"] == 0
        assert "tested_output_paths" not in rows[baseline]
    assert rows["certificate-visible-non-enforcing"]["certificate_visible"] is True
    assert rows["warning-layer"]["warning_attached"] is True
    enforced = rows["themegraph-certificate-enforcement"]
    assert enforced["unauthorized_statements_emitted"] == 0
    assert enforced["unauthorized_semantic_marks_emitted"] == 0
    assert enforced["unauthorized_requested_exports_emitted"] == 0
    assert enforced["lawful_fallbacks_preserved"] == 1


def test_schema_valid_record_does_not_establish_upstream_semantic_integrity() -> None:
    result = complete_benchmark()["evidence_integrity_trust_boundary"]

    assert result["schema_valid"] is True
    assert result["provenance_complete"] is True
    assert result["source_relation"] == ["event B", "event A"]
    assert result["faulty_adapter_typed_relation"] == ["event A", "event B"]
    assert result["requested_relation"] == ["event A", "event B"]
    assert result["source_semantics_contradict_typed_relation"] is True
    assert result["decision"] == "ADMIT"
    assert result["policy_conformant_admission"] is True
    assert result["semantic_authenticity_checked"] is False