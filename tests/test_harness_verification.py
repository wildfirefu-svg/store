from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import affected_tests
from scripts import apply_verified_claims
from scripts import run_verified_evidence_pack
from scripts import update_verified_claims
from scripts import verify_ci
from scripts import verify_runtime
from scripts import verify_smoke


def test_harness_scripts_route_to_harness_tests():
    for path in (
        "scripts/affected_tests.py",
        "scripts/apply_verified_claims.py",
        "scripts/run_verified_evidence_pack.py",
        "scripts/update_verified_claims.py",
        "scripts/verify_ci.py",
        "scripts/verify_runtime.py",
        "scripts/verify_smoke.py",
    ):
        assert affected_tests.map_file(path) == [
            "tests/test_harness_verification.py"
        ]


def test_affected_test_command_uses_workspace_temp_dir():
    command = affected_tests.pytest_command(["tests/test_harness_verification.py"])
    assert "--basetemp" in command
    basetemp = Path(command[command.index("--basetemp") + 1])
    assert basetemp.parent == affected_tests.PROJECT_ROOT / ".tmp"
    assert command[-2:] == ["-p", "no:cacheprovider"]


def test_runtime_elapsed_uses_monotonic_clock(monkeypatch):
    monkeypatch.setattr(verify_runtime.time, "monotonic", lambda: 11.75)
    assert verify_runtime._elapsed_seconds(10.0) == 1.75


def test_runtime_health_rejects_exited_child(monkeypatch):
    class ExitedProcess:
        def poll(self):
            return 1

    def unexpected_open(*args, **kwargs):
        raise AssertionError("health request must not run for an exited child")

    monkeypatch.setattr(verify_runtime.urllib.request, "urlopen", unexpected_open)
    ok, reason = verify_runtime.wait_for_health(
        "http://127.0.0.1:1/api/health", 1, ExitedProcess()
    )
    assert ok is False
    assert "exited" in reason


def test_cli_resolution_uses_explicit_environment_path(tmp_path):
    cli = tmp_path / "better-harness.mjs"
    cli.write_text("", encoding="utf-8")
    assert run_verified_evidence_pack.resolve_cli(
        {"BETTER_HARNESS_CLI": str(cli)}
    ) == cli


def test_cli_resolution_rejects_missing_explicit_path(tmp_path):
    missing = tmp_path / "missing.mjs"
    with pytest.raises(FileNotFoundError, match="BETTER_HARNESS_CLI"):
        run_verified_evidence_pack.resolve_cli(
            {"BETTER_HARNESS_CLI": str(missing)}
        )


def test_static_ci_claim_does_not_verify_remote_ci_status(tmp_path, monkeypatch):
    verified_path = tmp_path / "verified-claims.json"
    verified_path.write_text(
        json.dumps(
            {
                "generatedAt": "2026-08-06T00:00:00Z",
                "claims": [
                    {
                        "claim": "CI workflow configuration",
                        "status": "verified",
                        "command": "python scripts/verify_ci.py",
                        "details": {"resultFile": "verify-ci.result.json"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence_path = tmp_path / "project-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "evidenceSources": {
                    "unverifiedClaims": [
                        {"claim": "CI status", "status": "UNVERIFIED"}
                    ]
                },
                "reviewMatrix": [
                    {
                        "id": "static-evidence-boundary",
                        "evidence": {"unverified": ["CI status"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(apply_verified_claims, "VERIFIED_CLAIMS_FILE", verified_path)
    monkeypatch.setattr(sys, "argv", ["apply_verified_claims.py", str(evidence_path)])

    assert apply_verified_claims.main() == 0
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert [item["claim"] for item in evidence["evidenceSources"]["unverifiedClaims"]] == [
        "CI status"
    ]
    assert [item["claim"] for item in evidence["evidenceSources"]["verifiedClaims"]] == [
        "CI workflow configuration"
    ]


def test_ci_validation_rejects_test_job_without_required_steps(tmp_path, monkeypatch):
    ci_file = tmp_path / "ci.yml"
    ci_file.write_text(
        "name: CI\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    result_file = tmp_path / "verify-ci.result.json"
    monkeypatch.setattr(verify_ci, "CI_FILE", ci_file)
    monkeypatch.setattr(verify_ci, "RESULT_DIR", tmp_path)
    monkeypatch.setattr(verify_ci, "RESULT_FILE", result_file)

    assert verify_ci.main() == 1
    result = json.loads(result_file.read_text(encoding="utf-8"))
    assert result["status"] == "failed"


def test_ci_validation_does_not_borrow_steps_from_another_job(tmp_path, monkeypatch):
    ci_file = tmp_path / "ci.yml"
    ci_file.write_text(
        """name: CI
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo no validation
  decoy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
      - run: pytest
""",
        encoding="utf-8",
    )
    result_file = tmp_path / "verify-ci.result.json"
    monkeypatch.setattr(verify_ci, "CI_FILE", ci_file)
    monkeypatch.setattr(verify_ci, "RESULT_DIR", tmp_path)
    monkeypatch.setattr(verify_ci, "RESULT_FILE", result_file)

    assert verify_ci.main() == 1


def test_smoke_claim_is_scoped_to_focused_tests():
    assert verify_smoke.CLAIM == "focused smoke tests passed"


def test_verified_claims_use_ci_workflow_configuration_name(tmp_path, monkeypatch):
    results = {
        "tests passed": "verify-smoke.result.json",
        "CI workflow configuration": "verify-ci.result.json",
        "runtime behavior": "verify-runtime.result.json",
    }
    claim_files = {}
    for claim, name in results.items():
        path = tmp_path / name
        path.write_text(
            json.dumps(
                {
                    "status": "verified",
                    "command": name,
                    "exitCode": 0,
                    "finishedAt": "2026-08-06T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        claim_files[claim] = path
    output = tmp_path / "verified-claims.json"
    monkeypatch.setattr(update_verified_claims, "CLAIM_FILES", claim_files)
    monkeypatch.setattr(update_verified_claims, "OUTPUT_FILE", output)

    assert update_verified_claims.main() == 0
    claims = json.loads(output.read_text(encoding="utf-8"))["claims"]
    assert {claim["claim"] for claim in claims} == set(results)
    assert "CI status" not in {claim["claim"] for claim in claims}


def test_qoder_dev_skill_matches_source_and_has_windows_port_command():
    root = Path(__file__).resolve().parents[1]
    source = (root / ".reasonix/skills/dev.md").read_text(encoding="utf-8")
    registered = (root / ".qoder/skills/dev/SKILL.md").read_text(encoding="utf-8")
    assert registered == source
    assert "Get-NetTCPConnection" in registered
    assert "On Windows" in registered


def test_registered_skills_use_safe_executable_commands():
    root = Path(__file__).resolve().parents[1]
    for name in ("quality-check", "docker-up", "test-suite"):
        source = (root / f".reasonix/skills/{name}.md").read_text(encoding="utf-8")
        registered = (root / f".qoder/skills/{name}/SKILL.md").read_text(
            encoding="utf-8"
        )
        assert registered == source

    quality = (root / ".reasonix/skills/quality-check.md").read_text(encoding="utf-8")
    assert "python tests/expand_patterns.py" not in quality
    assert "validate_hallucination.py path/to/report.md path/to/chart.json" in quality
    assert "cross-school rule consistency" in quality
    assert "same input produces the same output across runs" not in quality

    docker = (root / ".reasonix/skills/docker-up.md").read_text(encoding="utf-8")
    dev = (root / ".reasonix/skills/dev.md").read_text(encoding="utf-8")
    assert ".deepseek_key" not in docker + dev
    assert ".anthropic_key" not in docker + dev
    assert "docker compose logs app" not in docker
    assert "docker compose logs api" in docker
    assert "${BAZI_API_PORT:-8000}" in docker
    assert "change `BAZI_API_PORT` in `.env`" in docker

    suite = (root / ".reasonix/skills/test-suite.md").read_text(encoding="utf-8")
    assert "affected_tests.py --run bazi_calculator.py" in suite


def test_ci_syntax_check_discovers_python_recursively():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "rglob('*.py')" in workflow
