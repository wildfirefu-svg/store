"""Behavior tests for .qoder/hooks guard scripts (design 2026-08-07 v2).

Protocol under test: block == exit 2 + reason on stderr; allow == exit 0.
"""
import json
import subprocess
import sys

from tests.harness_asset_helpers import PROJECT_ROOT

GUARD = PROJECT_ROOT / ".qoder" / "hooks" / "guard_data_artifacts.py"
REMIND = PROJECT_ROOT / ".qoder" / "hooks" / "remind_affected_tests.py"


def run_hook(script, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )


def write_payload(path):
    return {"tool_name": "Write", "tool_input": {"file_path": path}}


def bash_payload(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_guard_write_forbidden_json_denied():
    proc = run_hook(GUARD, write_payload("knowledge-base/ziping.md.json"))
    assert proc.returncode == 2
    assert "禁改" in proc.stderr.decode("utf-8")


def test_guard_write_forbidden_dataset_denied():
    proc = run_hook(GUARD, write_payload("benchmark/datasets/mingli_bench.jsonl"))
    assert proc.returncode == 2


def test_guard_edit_forbidden_data_denied():
    proc = run_hook(
        GUARD, {"tool_name": "Edit", "tool_input": {"file_path": "data/charts/1.json"}}
    )
    assert proc.returncode == 2


def test_guard_write_allowed_file_passes():
    proc = run_hook(GUARD, write_payload("api_server.py"))
    assert proc.returncode == 0


def test_guard_write_unrelated_json_passes():
    proc = run_hook(GUARD, write_payload("docs/notes.json"))
    assert proc.returncode == 0


def test_guard_bash_explicit_delete_denied():
    proc = run_hook(
        GUARD, bash_payload("Remove-Item knowledge-base/ziping.md.json")
    )
    assert proc.returncode == 2
    assert "禁改" in proc.stderr.decode("utf-8")


def test_guard_bash_redirect_write_denied():
    proc = run_hook(GUARD, bash_payload("echo [] > data/cases_real_db.json"))
    assert proc.returncode == 2


def test_guard_bash_copy_write_denied():
    proc = run_hook(GUARD, bash_payload("cp evil.json data/cases_real_db.json"))
    assert proc.returncode == 2


def test_guard_bash_read_only_passes():
    proc = run_hook(GUARD, bash_payload("cat knowledge-base/ziping.md.json"))
    assert proc.returncode == 0


def test_guard_bash_dynamic_path_is_known_gap_passes():
    # 动态拼接路径不在保护承诺内（spec §4.3 如实表述），当前放行。
    proc = run_hook(GUARD, bash_payload('Remove-Item "$KB_DIR/$NAME.json"'))
    assert proc.returncode == 0


def test_guard_unknown_tool_passes():
    proc = run_hook(GUARD, {"tool_name": "Read", "tool_input": {}})
    assert proc.returncode == 0


def test_guard_malformed_json_passes_open():
    # fail-open：stdin 不是合法 JSON 时放行（守护脚本不得阻塞会话）。
    proc = subprocess.run(
        [sys.executable, str(GUARD)], input=b"not-json", capture_output=True, timeout=30
    )
    assert proc.returncode == 0


def test_guard_non_dict_json_passes_open():
    # 合法 JSON 但非事件对象：同样 fail-open。
    proc = subprocess.run(
        [sys.executable, str(GUARD)], input=b"null", capture_output=True, timeout=30
    )
    assert proc.returncode == 0


# remind 脚本属 Task 4；当前失败原因是脚本尚未创建（解释器 exit 2），非行为回归。
def test_remind_scripts_edit_emits_hint():
    proc = run_hook(REMIND, write_payload("scripts/verify_smoke.py"))
    assert proc.returncode == 0
    assert "affected_tests" in proc.stdout.decode("utf-8")


def test_remind_benchmark_edit_emits_hint():
    proc = run_hook(REMIND, write_payload("benchmark/runners/profiles.py"))
    assert proc.returncode == 0
    assert "affected_tests" in proc.stdout.decode("utf-8")


def test_remind_unrelated_edit_silent():
    proc = run_hook(REMIND, write_payload("api_server.py"))
    assert proc.returncode == 0
    assert proc.stdout == b""
