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
