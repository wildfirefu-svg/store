from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_phase5_c2_generalization as phase5


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def sample_case(case_id: str = "c1", answer: str = "B", domain: str = "wealth") -> dict:
    return {
        "case_id": case_id,
        "answer": answer,
        "domain": domain,
        "question": "命主财运如何？",
        "options": ["A 普通", "B 富裕", "C 破财", "D 平稳"],
        "source_year": "2021",
        "person": {
            "person_id": f"p-{case_id}",
            "gender": "male",
            "birth": {
                "year": 1990,
                "month": 1,
                "day": 2,
                "hour": 3,
                "minute": 0,
                "place": "北京",
            },
        },
    }


def fake_enrich(row: dict) -> dict:
    return {
        **row,
        "chart_input": {
            "shishen_stats": {"counts": {"正财": 1}, "missing": []},
            "branch_relations": [],
            "shensha": [],
            "wuxing_stats": {"missing": [], "strongest": "木", "weakest": "水"},
        },
    }


def test_enrich_dataset_preserves_protected_fields_and_hash(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    output = tmp_path / "enriched.jsonl"
    rows = [sample_case("c1"), sample_case("c2", answer="C")]
    write_jsonl(source, rows)

    metadata = phase5.enrich_dataset(
        source,
        output,
        enrich_fn=fake_enrich,
        expected_rows=2,
    )

    enriched = phase5.load_jsonl(output)
    assert metadata["row_count"] == 2
    assert metadata["chart_input_coverage"] == 1.0
    assert metadata["sha256"] == phase5.sha256_file(output)
    assert [row["case_id"] for row in enriched] == ["c1", "c2"]
    assert [row["answer"] for row in enriched] == ["B", "C"]
    assert [row["person"] for row in enriched] == [row["person"] for row in rows]
    assert all(row["chart_input"] for row in enriched)


def test_validate_enriched_rejects_duplicate_case_id(tmp_path: Path):
    source_rows = [sample_case("c1"), sample_case("c2")]
    enriched_rows = [fake_enrich(sample_case("c1")), fake_enrich(sample_case("c1"))]

    with pytest.raises(ValueError, match="duplicate case_id"):
        phase5.validate_enriched_rows(source_rows, enriched_rows)


def test_validate_enriched_rejects_answer_mutation():
    original = sample_case()
    changed = fake_enrich({**original, "answer": "D"})

    with pytest.raises(ValueError, match="protected field changed"):
        phase5.validate_enriched_rows([original], [changed])


def test_enrich_dataset_requires_expected_holdout_size(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    write_jsonl(source, [sample_case("c1")])

    with pytest.raises(ValueError, match="expected 40 rows"):
        phase5.enrich_dataset(source, tmp_path / "out.jsonl", enrich_fn=fake_enrich)


def test_validate_enriched_rejects_missing_core_chart_signals():
    source = sample_case()
    incomplete = {
        **source,
        "chart_input": {
            "shishen_stats": {"counts": {}},
            "wuxing_stats": {"strongest": None},
        },
    }

    with pytest.raises(ValueError, match="incomplete chart signals"):
        phase5.validate_enriched_rows([source], [incomplete])


def test_classify_c2_applicability_separates_effective_and_noop_cases():
    cases = [sample_case("active"), sample_case("noop")]
    result = phase5.classify_c2_applicability(
        cases,
        score_fn=lambda case: [{"score": 50}] if case["case_id"] == "active" else [],
    )

    assert result == {
        "c2_effective_cases": 1,
        "c2_noop_cases": 1,
        "c2_effective_case_ids": ["active"],
        "c2_noop_case_ids": ["noop"],
        "c2_effective_rate": 0.5,
    }


def test_dirty_scope_requires_explicit_override():
    dirty = {"benchmark/runners/per_option_scorer.py": "??"}

    with pytest.raises(RuntimeError, match="--allow-dirty-scope"):
        phase5.enforce_dirty_scope(dirty, allow_dirty_scope=False)

    phase5.enforce_dirty_scope(dirty, allow_dirty_scope=True)


def test_manifest_resume_requires_exact_fingerprint(tmp_path: Path):
    path = tmp_path / "manifest.json"
    expected = {"fingerprint": "abc", "run_id": "r1"}
    phase5.write_json(path, expected)

    assert phase5.load_or_validate_manifest(path, expected, resume=True) == expected
    with pytest.raises(RuntimeError, match="manifest mismatch"):
        phase5.load_or_validate_manifest(
            path,
            {"fingerprint": "changed", "run_id": "r1"},
            resume=True,
        )


def test_existing_manifest_requires_resume(tmp_path: Path):
    path = tmp_path / "manifest.json"
    phase5.write_json(path, {"fingerprint": "abc"})

    with pytest.raises(RuntimeError, match="--resume"):
        phase5.load_or_validate_manifest(path, {"fingerprint": "abc"}, resume=False)


def test_resume_requires_existing_manifest(tmp_path: Path):
    with pytest.raises(RuntimeError, match="cannot resume missing manifest"):
        phase5.load_or_validate_manifest(
            tmp_path / "missing.json",
            {"fingerprint": "abc"},
            resume=True,
        )


def test_manifest_declares_explicit_fingerprint_scope(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    config = phase5.ExperimentConfig("r1", tmp_path, (2021, 2022))

    manifest = phase5.build_manifest(config, datasets={}, scope_status={})

    assert manifest["fingerprint_scope"] == {
        "coverage": "explicit_experiment_files_only",
        "files": [],
        "indirect_dependencies_fingerprinted": False,
    }
    assert manifest["seal_audit_note"] == phase5.SEAL_AUDIT_NOTE


def test_fixed_environment_rejects_rag(monkeypatch):
    monkeypatch.setenv("BAZI_RAG", "1")

    with pytest.raises(RuntimeError, match="BAZI_RAG"):
        phase5.assert_fixed_environment()


def passing_metrics() -> dict:
    return {
        "top_score_hit_rate": 0.36,
        "score_answer_correlation": 0.11,
        "neutral_option_rate": 0.49,
        "strong_signal_option_rate": 0.31,
    }


def test_offline_gate_reports_values_thresholds_margins():
    result = phase5.evaluate_offline_gate(passing_metrics())

    assert result["passed"] is True
    assert result["metrics"]["top_score_hit_rate"] == {
        "value": 0.36,
        "operator": ">",
        "threshold": 0.35,
        "margin": pytest.approx(0.01),
        "passed": True,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("top_score_hit_rate", 0.35),
        ("score_answer_correlation", 0.10),
        ("neutral_option_rate", 0.50),
        ("strong_signal_option_rate", 0.30),
    ],
)
def test_offline_gate_uses_strict_boundaries(name: str, value: float):
    metrics = passing_metrics()
    metrics[name] = value
    assert phase5.evaluate_offline_gate(metrics)["passed"] is False


def test_2023_cannot_be_read_without_final_unlock(tmp_path: Path):
    config = phase5.ExperimentConfig(
        run_id="r1",
        root=tmp_path,
        years=(2023,),
        final_2023=False,
    )

    with pytest.raises(RuntimeError, match="2023 is sealed"):
        phase5.assert_year_access(config, 2023, prior_summary=None)


def test_2023_requires_prior_results_and_frozen_candidate(tmp_path: Path):
    config = phase5.ExperimentConfig(
        run_id="r1",
        root=tmp_path,
        years=(2023,),
        final_2023=True,
        candidate_id="candidate-a",
    )
    prior = {"years": {"2021": {}, "2022": {}}, "decision": "NON_INFERIOR"}
    phase5.write_json(tmp_path / "manifest.json", {"run_id": "r1"})

    phase5.assert_year_access(config, 2023, prior_summary=prior)
    with pytest.raises(RuntimeError, match="candidate_id"):
        phase5.assert_year_access(
            phase5.ExperimentConfig(
                run_id="r1",
                root=tmp_path,
                years=(2023,),
                final_2023=True,
            ),
            2023,
            prior_summary=prior,
        )


def test_balanced_schedule_is_reproducible():
    cases = [sample_case(f"c{i}") for i in range(5)]

    first = phase5.build_schedule(cases, seed=7)
    second = phase5.build_schedule(cases, seed=7)

    assert first == second
    assert abs(
        sum(pair[0] == "direct" for _, pair in first)
        - sum(pair[0] == "direct_c2" for _, pair in first)
    ) <= 1
    assert all(set(pair) == {"direct", "direct_c2"} for _, pair in first)


def test_each_year_has_a_recorded_derived_schedule_seed(tmp_path: Path):
    config = phase5.ExperimentConfig("r1", tmp_path, (2021, 2022), seed=7)

    assert phase5.year_schedule_seed(config, 2021) == 2028
    assert phase5.year_schedule_seed(config, 2022) == 2029


def test_run_attempt_passes_no_case_details_and_persists(tmp_path: Path):
    calls = []

    def fake_runner(cases, provider, model, prompt_version, **kwargs):
        calls.append(kwargs)
        case = cases[0]
        return {
            "case_details": [{
                "case_id": case["case_id"],
                "expected_answer": case["answer"],
                "predicted_answer": "B",
                "raw_answer": "B",
                "parser_source": "legacy",
                "parser_valid": True,
                "correct": True,
                "call_success": True,
                "phase4_option_scores": [],
            }],
            "failed_cases": [],
        }

    path = tmp_path / "attempts.jsonl"
    config = phase5.ExperimentConfig("r1", tmp_path, (2021,))
    phase5.write_json(config.root / "manifest.json", {"fingerprint": "fp"})
    row = phase5.run_attempt(
        config,
        2021,
        sample_case(),
        "direct_c2",
        1,
        path,
        fake_runner,
    )

    assert calls[0]["case_details_jsonl"] is None
    assert calls[0]["phase4_direct_c2"] is True
    assert calls[0]["n_samples"] == 1
    assert row["arm"] == "direct_c2"
    assert phase5.load_jsonl(path) == [row]


def test_completed_attempt_is_not_called_again(tmp_path: Path):
    path = tmp_path / "attempts.jsonl"
    existing = {
        "run_id": "r1",
        "year": 2021,
        "case_id": "c1",
        "arm": "direct",
        "attempt": 1,
    }
    phase5.append_jsonl(path, existing)
    calls = []

    result = phase5.run_attempt(
        phase5.ExperimentConfig("r1", tmp_path, (2021,), resume=True),
        2021,
        sample_case(),
        "direct",
        1,
        path,
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert result == existing
    assert calls == []


def test_failure_marker_is_persisted(tmp_path: Path):
    def failing_runner(*args, **kwargs):
        raise TimeoutError("temporary timeout")

    path = tmp_path / "attempts.jsonl"
    phase5.write_json(tmp_path / "manifest.json", {"fingerprint": "fp"})
    row = phase5.run_attempt(
        phase5.ExperimentConfig("r1", tmp_path, (2021,)),
        2021,
        sample_case(),
        "direct",
        1,
        path,
        failing_runner,
    )

    assert row["call_success"] is False
    assert row["parser_valid"] is False
    assert row["failure"] == "TimeoutError: temporary timeout"
    assert len(phase5.load_jsonl(path)) == 1


def attempt(case_id: str, arm: str, number: int, choice: str | None, valid: bool = True) -> dict:
    return {
        "run_id": "r1",
        "year": 2021,
        "case_id": case_id,
        "arm": arm,
        "attempt": number,
        "predicted_answer": choice,
        "expected_answer": "B",
        "parser_valid": valid,
        "correct": valid and choice == "B",
        "call_success": valid,
        "retrieved_answer_leak": False,
    }


def test_only_initial_disagreements_are_retested(tmp_path: Path):
    rows = [
        attempt("same", "direct", 1, "B"),
        attempt("same", "direct_c2", 1, "B"),
        attempt("diff", "direct", 1, "A"),
        attempt("diff", "direct_c2", 1, "B"),
    ]

    assert phase5.disagreement_case_ids(rows) == ["diff"]


def test_majority_vote_uses_only_valid_votes_and_marks_tie_unresolved():
    majority = phase5.resolve_arm([
        attempt("c1", "direct", 1, "B"),
        attempt("c1", "direct", 2, "B"),
        attempt("c1", "direct", 3, None, valid=False),
    ])
    tie = phase5.resolve_arm([
        attempt("c1", "direct", 1, "A"),
        attempt("c1", "direct", 2, "B"),
        attempt("c1", "direct", 3, None, valid=False),
    ])

    assert majority["choice"] == "B"
    assert majority["unresolved"] is False
    assert tie["choice"] is None
    assert tie["unresolved"] is True


def test_all_invalid_is_counted_separately():
    result = phase5.resolve_arm([
        attempt("c1", "direct", 1, None, valid=False),
        attempt("c1", "direct", 2, None, valid=False),
        attempt("c1", "direct", 3, None, valid=False),
    ])

    assert result["unresolved"] is True
    assert result["all_invalid"] is True


def test_repeat_consistency_distinguishes_unanimous_majority_and_unresolved():
    rows = [
        attempt("same", "direct", 1, "B"),
        attempt("same", "direct", 2, "B"),
        attempt("same", "direct", 3, "B"),
        attempt("split", "direct_c2", 1, "A"),
        attempt("split", "direct_c2", 2, "B"),
        attempt("split", "direct_c2", 3, "B"),
        attempt("invalid", "direct", 1, "A"),
        attempt("invalid", "direct", 2, "B"),
        attempt("invalid", "direct", 3, None, valid=False),
    ]

    assert phase5.summarize_repeat_consistency(rows) == {
        "unanimous": 1,
        "majority_2_to_1": 1,
        "unresolved": 1,
    }


def test_initial_regression_stop_triggers_at_four():
    rows = []
    for index in range(4):
        case_id = f"c{index}"
        rows.extend([
            attempt(case_id, "direct", 1, "B"),
            attempt(case_id, "direct_c2", 1, "A"),
        ])

    assert phase5.count_initial_rescues_regressions(rows) == {"rescues": 0, "regressions": 4}
    assert phase5.should_stop_after_initial(rows) is True


def test_exact_mcnemar_uses_two_sided_binomial():
    assert phase5.exact_mcnemar_pvalue(0, 0) == 1.0
    assert phase5.exact_mcnemar_pvalue(1, 5) == pytest.approx(0.21875)
    assert phase5.exact_mcnemar_pvalue(5, 1) == pytest.approx(0.21875)


def decision_input(rescues: int, regressions: int) -> dict:
    return {
        "total": 120,
        "direct_correct": 40,
        "c2_correct": 40 + rescues - regressions,
        "rescues": rescues,
        "regressions": regressions,
        "non_degrading_years": 2,
        "parser_valid_rate": 0.96,
        "confirmed_answer_leaks": 0,
    }


def test_final_decision_boundaries():
    assert phase5.decide_final(decision_input(3, 2))["decision"] == "PROMOTE"
    assert phase5.decide_final(decision_input(2, 2))["decision"] == "NON_INFERIOR"
    assert phase5.decide_final(decision_input(2, 3))["decision"] == "ROLLBACK"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("c2_correct", 39),
        ("non_degrading_years", 1),
        ("regressions", 13),
        ("parser_valid_rate", 0.949),
        ("confirmed_answer_leaks", 1),
    ],
)
def test_any_hard_gate_failure_rolls_back(field: str, value):
    metrics = decision_input(3, 2)
    metrics[field] = value
    assert phase5.decide_final(metrics)["decision"] == "ROLLBACK"


def test_summary_stratifies_c2_applicability_and_parser_sources():
    results = [
        {
            "case_id": "active",
            "year": 2021,
            "domain": "wealth",
            "c2_effective": True,
            "direct": {"correct": False, "all_invalid": False, "unresolved": False},
            "direct_c2": {"correct": True, "all_invalid": False, "unresolved": False},
        },
        {
            "case_id": "noop",
            "year": 2021,
            "domain": "unknown",
            "c2_effective": False,
            "direct": {"correct": True, "all_invalid": False, "unresolved": False},
            "direct_c2": {"correct": True, "all_invalid": False, "unresolved": False},
        },
    ]
    attempts = [
        {"case_id": "active", "arm": "direct", "parser_source": "final_answer", "parser_valid": True},
        {"case_id": "active", "arm": "direct_c2", "parser_source": "confidence", "parser_valid": True},
    ]

    summary = phase5.summarize_stable_results(results, attempts)

    assert summary["by_c2_applicability"]["effective"]["rescues"] == 1
    assert summary["by_c2_applicability"]["noop"]["both_correct"] == 1
    assert summary["parser_source_by_arm"] == {
        "direct": {"final_answer": 1},
        "direct_c2": {"confidence": 1},
    }


def test_run_validation_uses_fake_runner_and_writes_summary(tmp_path: Path, monkeypatch):
    cases = [sample_case("c1"), sample_case("c2")]
    for year in (2021, 2022):
        year_rows = [{**row, "source_year": str(year)} for row in cases]
        write_jsonl(tmp_path / f"source-{year}.jsonl", year_rows)

    monkeypatch.setattr(phase5, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    monkeypatch.setattr(phase5, "experiment_scope_status", dict)
    monkeypatch.setattr(phase5, "enrich_row", fake_enrich)
    monkeypatch.setattr(
        phase5,
        "summarize_scores",
        lambda rows: {**passing_metrics(), "n_cases": len(rows), "cases": []},
    )

    def fake_runner(cases, provider, model, prompt_version, **kwargs):
        case = cases[0]
        return {
            "case_details": [{
                "case_id": case["case_id"],
                "expected_answer": case["answer"],
                "predicted_answer": case["answer"],
                "raw_answer": case["answer"],
                "parser_source": "legacy",
                "parser_valid": True,
                "correct": True,
                "call_success": True,
                "phase4_option_scores": [],
                "retrieved_answer_leak": False,
            }],
            "failed_cases": [],
        }

    config = phase5.ExperimentConfig("r1", tmp_path / "work", (2021, 2022))
    source_paths = {year: tmp_path / f"source-{year}.jsonl" for year in config.years}
    result = phase5.run_validation(
        config,
        source_paths,
        runner=fake_runner,
        expected_rows=2,
    )

    assert result["decision"] == "NON_INFERIOR"
    assert result["total"] == 4
    assert (config.root / "summary.json").is_file()
    assert (config.root / "runs" / "2021" / "attempts.jsonl").is_file()
    initial_manifest_hash = phase5.sha256_file(config.root / "manifest.json")

    rows_2023 = [{**row, "source_year": "2023"} for row in cases]
    source_2023 = tmp_path / "source-2023.jsonl"
    write_jsonl(source_2023, rows_2023)
    final_config = phase5.ExperimentConfig(
        "r1",
        config.root,
        (2023,),
        final_2023=True,
        candidate_id="candidate-direct-c2-v1",
    )
    final = phase5.run_validation(
        final_config,
        {2023: source_2023},
        runner=fake_runner,
        expected_rows=2,
    )

    assert final["total"] == 6
    assert (config.root / "final_manifest.json").is_file()
    assert phase5.sha256_file(config.root / "manifest.json") == initial_manifest_hash
    archive_dir = tmp_path / "docs" / "phase5" / "r1"
    assert (archive_dir / "manifest.json").is_file()
    assert (archive_dir / "summary.json").is_file()
    assert (archive_dir / "report.md").is_file()


def test_run_validation_rejects_rag_before_model_call(tmp_path: Path, monkeypatch):
    called = {"runner": False}

    def forbidden_runner(*args, **kwargs):
        called["runner"] = True
        raise AssertionError("runner must not be called")

    monkeypatch.setenv("BAZI_RAG", "1")
    config = phase5.ExperimentConfig("rag-off", tmp_path / "work", (2021, 2022))

    with pytest.raises(RuntimeError, match="BAZI_RAG"):
        phase5.run_validation(config, {}, runner=forbidden_runner)

    assert called["runner"] is False


def test_final_2023_offline_failure_preserves_prior_results(tmp_path: Path, monkeypatch):
    work = tmp_path / "work"
    source_2023 = tmp_path / "source-2023.jsonl"
    write_jsonl(source_2023, [{**sample_case("final-c1"), "source_year": "2023"}])
    prior_case_results = [{"case_id": "prior-c1", "year": 2021}]
    prior_years = {
        "2021": {"total": 40, "direct_correct": 10, "c2_correct": 11},
        "2022": {"total": 40, "direct_correct": 12, "c2_correct": 12},
    }
    prior_summary = {
        "decision": "NON_INFERIOR",
        "years": prior_years,
        "case_results": prior_case_results,
        "offline": {
            "2021": {"gate": {"passed": True}},
            "2022": {"gate": {"passed": True}},
        },
    }
    phase5.write_json(work / "manifest.json", {"run_id": "r1"})
    phase5.write_json(work / "summary.json", prior_summary)
    monkeypatch.setattr(phase5, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    monkeypatch.setattr(phase5, "experiment_scope_status", dict)
    monkeypatch.setattr(phase5, "enrich_row", fake_enrich)
    monkeypatch.setattr(
        phase5,
        "summarize_scores",
        lambda rows: {
            **passing_metrics(),
            "top_score_hit_rate": 0.35,
            "n_cases": len(rows),
            "cases": [],
        },
    )
    called = {"runner": False}

    def forbidden_runner(*args, **kwargs):
        called["runner"] = True
        raise AssertionError("runner must not be called after offline gate failure")

    config = phase5.ExperimentConfig(
        "r1",
        work,
        (2023,),
        final_2023=True,
        candidate_id="candidate-direct-c2-v1",
    )
    summary = phase5.run_validation(
        config,
        {2023: source_2023},
        runner=forbidden_runner,
        expected_rows=1,
    )

    assert summary["decision"] == "ROLLBACK"
    assert summary["reason"] == "offline_gate_failed"
    assert summary["years"] == prior_years
    assert summary["case_results"] == prior_case_results
    assert set(summary["offline"]) == {"2021", "2022", "2023"}
    assert called["runner"] is False


def test_run_id_rejects_path_traversal():
    with pytest.raises(ValueError, match="run_id must be"):
        phase5.validate_run_id("../overwrite")


def test_run_validation_persists_auditable_year_stop(tmp_path: Path, monkeypatch):
    cases = [sample_case(f"c{i}") for i in range(4)]
    source = tmp_path / "source-2021.jsonl"
    write_jsonl(source, cases)
    monkeypatch.setattr(phase5, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(phase5, "EXPERIMENT_SCOPE", ())
    monkeypatch.setattr(phase5, "git_output", lambda *args: "deadbeef")
    monkeypatch.setattr(phase5, "experiment_scope_status", dict)
    monkeypatch.setattr(phase5, "enrich_row", fake_enrich)
    monkeypatch.setattr(
        phase5,
        "summarize_scores",
        lambda rows: {**passing_metrics(), "n_cases": len(rows), "cases": []},
    )

    def harmful_c2_runner(cases, provider, model, prompt_version, **kwargs):
        case = cases[0]
        choice = "A" if kwargs["phase4_direct_c2"] else case["answer"]
        return {
            "case_details": [{
                "case_id": case["case_id"],
                "expected_answer": case["answer"],
                "predicted_answer": choice,
                "raw_answer": choice,
                "parser_source": "legacy",
                "parser_valid": True,
                "correct": choice == case["answer"],
                "call_success": True,
                "phase4_option_scores": [],
                "retrieved_answer_leak": False,
            }],
            "failed_cases": [],
        }

    config = phase5.ExperimentConfig("stop-r1", tmp_path / "stop-work", (2021,))
    summary = phase5.run_validation(
        config,
        {2021: source},
        runner=harmful_c2_runner,
        expected_rows=4,
    )

    assert summary["decision"] == "ROLLBACK"
    assert summary["reason"] == "year_stop"
    assert summary["initial_stop_metrics"]["regressions"] == 4
    assert len(summary["case_results"]) == 4
    assert summary["attempts_seen"] == 8
    persisted = json.loads((config.root / "summary.json").read_text(encoding="utf-8"))
    assert persisted == summary


def test_render_report_contains_gate_evidence():
    summary = {
        **decision_input(2, 2),
        "decision": "NON_INFERIOR",
        "gates": {"c2_not_worse": True},
        "mcnemar_exact_p": 1.0,
        "all_invalid": 0,
        "unresolved": 0,
        "both_correct": 0,
        "both_wrong": 0,
        "by_year": {},
        "by_domain": {},
        "offline": {},
    }
    report = phase5.render_report(summary, manifest_sha256="abc123")

    assert "NON_INFERIOR" in report
    assert "McNemar" in report
    assert "Discordant pairs: 4" in report
    assert "fewer than 10 discordant pairs" in report
    assert "abc123" in report
    assert "MingLi-Bench" not in report


def test_promote_report_recommends_mingli_without_inventing_command():
    summary = {
        **decision_input(3, 2),
        "decision": "PROMOTE",
        "gates": {},
        "mcnemar_exact_p": 0.5,
        "all_invalid": 0,
        "unresolved": 0,
        "both_correct": 0,
        "both_wrong": 0,
        "by_year": {},
        "by_domain": {},
        "offline": {},
    }
    report = phase5.render_report(summary, manifest_sha256="abc123")

    assert "进入 MingLi-Bench 非退化验证" in report
    assert "--c2-enabled" not in report
