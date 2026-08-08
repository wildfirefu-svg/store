from __future__ import annotations
import pytest

def test_phase6_context_accepts_time_context_injection():
    from benchmark.runners.run_benchmark import Phase6Context
    ctx = Phase6Context(time_context_injection="on")
    assert ctx.time_context_injection == "on"

def test_resume_manifest_includes_time_context_injection():
    from benchmark.runners.run_benchmark import RESUME_MANIFEST_FIELDS
    assert "time_context_injection" in RESUME_MANIFEST_FIELDS

def test_resume_manifest_includes_temporal_routed_cases_sha256():
    from benchmark.runners.run_benchmark import RESUME_MANIFEST_FIELDS
    assert "temporal_routed_cases_sha256" in RESUME_MANIFEST_FIELDS

def test_reasoned_arm_map_includes_b1a_time_off_on():
    from benchmark.runners.run_benchmark import _REASONED_ARM_MAP
    assert "b1a_time_off" in _REASONED_ARM_MAP
    assert "b1a_time_on" in _REASONED_ARM_MAP
    assert _REASONED_ARM_MAP["b1a_time_off"] == "none"
    assert _REASONED_ARM_MAP["b1a_time_on"] == "none"

def test_code_scope_includes_bazi_time_context():
    from benchmark.runners.run_benchmark import _CODE_SCOPE
    assert "benchmark/formatters/bazi_time_context.py" in _CODE_SCOPE

def test_cli_to_prompt_off_on_different():
    """CLI --time-context-injection off vs on generate different prompts."""
    import json
    from benchmark.formatters.chart_context import render_reasoned_context
    path = "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl"
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    case = rows[0]  # any case
    off = render_reasoned_context(case, "v1", "none", time_context_injection="off")
    on = render_reasoned_context(case, "v1", "none", time_context_injection="on", route_state="ROUTED_WITHOUT_TARGETS")
    assert off != on

def test_prompt_diff_only_in_temporal_block():
    """off/on prompt diff is ONLY in temporal context section."""
    import json
    from benchmark.formatters.chart_context import render_reasoned_context
    path = "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl"
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    from benchmark.formatters.bazi_time_context import detect_temporal_rules, extract_target_years, classify_route_state
    case = None
    for row in rows:
        rules = detect_temporal_rules(row.get("question",""), row.get("options",[]))
        if rules:
            birth_year = row.get("birth_year") or row.get("person",{}).get("birth",{}).get("year")
            years = extract_target_years(row["question"], row["options"], birth_year)
            state = classify_route_state(rules, years)
            if state.name == "ROUTED_WITHOUT_TARGETS":
                case = row
                break
    if case is None:
        pytest.skip("No ROUTED_WITHOUT_TARGETS case found")
    off = render_reasoned_context(case, "v1", "none", time_context_injection="off")
    on = render_reasoned_context(case, "v1", "none", time_context_injection="on", route_state="ROUTED_WITHOUT_TARGETS")
    # The non-temporal part of off must be a prefix of on
    assert on.startswith(off)

def test_detail_records_temporal_route_state():
    """detail.jsonl each row has temporal_route_state."""
    from benchmark.runners.run_benchmark import compute_detail_provenance
    state, sha = compute_detail_provenance({}, "ROUTED_WITH_TARGETS", "off")
    assert state == "ROUTED_WITH_TARGETS"
    assert sha is None  # off -> null

def test_detail_sha_on_routed_is_actual_context_sha():
    """on + ROUTED_WITH_TARGETS -> actual TimeContext SHA."""
    from benchmark.runners.run_benchmark import compute_detail_provenance
    # This needs a real case to build TimeContext
    import json
    path = "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl"
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    from benchmark.formatters.bazi_time_context import detect_temporal_rules, extract_target_years, classify_route_state
    for row in rows:
        rules = detect_temporal_rules(row.get("question",""), row.get("options",[]))
        if "R6" in rules:
            birth_year = row.get("birth_year") or row.get("person",{}).get("birth",{}).get("year")
            years = extract_target_years(row["question"], row["options"], birth_year)
            state = classify_route_state(rules, years)
            if state.name == "ROUTED_WITH_TARGETS":
                state_val, sha = compute_detail_provenance(row, "ROUTED_WITH_TARGETS", "on")
                assert sha is not None
                assert len(sha) == 64
                return
    pytest.skip("No ROUTED_WITH_TARGETS case found")

def test_detail_sha_off_is_null():
    from benchmark.runners.run_benchmark import compute_detail_provenance
    _, sha = compute_detail_provenance({}, "ROUTED_WITH_TARGETS", "off")
    assert sha is None

def test_detail_route_state_invariant_to_injection():
    """Same case off/on records same route_state."""
    from benchmark.runners.run_benchmark import compute_detail_provenance
    state_off, _ = compute_detail_provenance({}, "ROUTED_WITH_TARGETS", "off")
    state_on, _ = compute_detail_provenance({}, "ROUTED_WITH_TARGETS", "on")
    assert state_off == state_on

def test_load_routed_manifest_returns_full_frozen_item():
    from benchmark.runners.run_benchmark import load_routed_manifest
    manifest = load_routed_manifest("docs/phase6/6d/temporal_routed_cases.json")
    # Check first entry has all fields
    for key, item in manifest.items():
        assert "route_state" in item
        assert "matched_rules" in item
        assert "target_years" in item
        break


def test_runtime_target_years_match_frozen_manifest():
    """Runtime target_years must match frozen manifest exactly."""
    import json
    from benchmark.runners.run_benchmark import load_routed_manifest, _lookup_routed_entry
    manifest = load_routed_manifest("docs/phase6/6d/temporal_routed_cases.json")
    path = "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl"
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    for row in rows:
        case_id = str(row.get("case_id", ""))
        year = str(row.get("source_year", ""))
        entry = _lookup_routed_entry(row, manifest)
        if entry and entry.get("route_state") == "ROUTED_WITH_TARGETS":
            # Verify the frozen target_years are used, not re-extracted
            frozen_years = tuple(entry.get("target_years", []))
            assert len(frozen_years) > 0
            # The manifest entry target_years should match what build_time_context would produce
            from benchmark.formatters.bazi_time_context import build_time_context, TemporalRouteState
            ctx = build_time_context(row, TemporalRouteState.ROUTED_WITH_TARGETS, frozen_target_years=frozen_years)
            if ctx is not None:
                assert tuple(ctx.target_years) == frozen_years
            return
    pytest.skip("No ROUTED_WITH_TARGETS case found")


def test_prompt_uses_frozen_target_years_not_reextracted():
    """When manifest target_years differ from re-extracted, prompt must use manifest."""
    import json
    from benchmark.runners.run_benchmark import build_benchmark_prompt, load_routed_manifest

    manifest = load_routed_manifest("docs/phase6/6d/temporal_routed_cases.json")
    path = "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl"
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

    for row in rows:
        case_id = str(row.get("case_id", ""))
        year = str(row.get("source_year", ""))
        key = (year, case_id)
        if key not in manifest:
            continue
        entry = manifest[key]
        if entry.get("route_state") != "ROUTED_WITH_TARGETS":
            continue
        frozen_years = tuple(entry.get("target_years", []))
        if not frozen_years:
            continue

        prompt_frozen = build_benchmark_prompt(
            row, method='direct_choice', chart_schema_version='v1',
            profile_formatter='format_reasoned_choice_prompt', ziwei_arm='none',
            time_context_injection='on', route_state='ROUTED_WITH_TARGETS',
            frozen_target_years=frozen_years)

        prompt_reextracted = build_benchmark_prompt(
            row, method='direct_choice', chart_schema_version='v1',
            profile_formatter='format_reasoned_choice_prompt', ziwei_arm='none',
            time_context_injection='on', route_state='ROUTED_WITH_TARGETS')

        # If frozen vs re-extracted differ, frozen years must be present
        if prompt_frozen != prompt_reextracted:
            for y in frozen_years:
                assert str(y) in prompt_frozen, f"frozen year {y} not in prompt"

        # The prompt must contain the frozen target year
        for y in frozen_years:
            assert str(y) in prompt_frozen, f"frozen year {y} missing from prompt"
        return

    pytest.skip("No ROUTED_WITH_TARGETS case with target_years found")
