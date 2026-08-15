"""Stage 1: run manifest build/verify + approval-commit reachability (B1 可达/悬空)."""
from __future__ import annotations
import subprocess
from pathlib import Path
import pytest
from scripts.run_manifest import build_run_manifest, verify_run_manifest, verify_approval_commit_reachable

ROOT = Path(__file__).resolve().parent.parent


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _tmp_git(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo


def test_run_manifest_build_verify_ok():
    m = build_run_manifest(run_id="R1", approval_commit="a" * 40)
    verify_run_manifest(m, expected_approval_commit="a" * 40)


def test_run_manifest_missing_field_rejected():
    m = build_run_manifest(run_id="R1", approval_commit="a" * 40)
    del m["approval_commit"]
    with pytest.raises(ValueError, match="approval_commit"):
        verify_run_manifest(m, expected_approval_commit="a" * 40)


def test_run_manifest_approval_commit_mismatch_rejected():
    m = build_run_manifest(run_id="R1", approval_commit="a" * 40)
    with pytest.raises(ValueError, match="mismatch"):
        verify_run_manifest(m, expected_approval_commit="b" * 40)


def test_run_manifest_non_40_char_rejected():
    m = build_run_manifest(run_id="R1", approval_commit="short")
    with pytest.raises(ValueError, match="40-char"):
        verify_run_manifest(m, expected_approval_commit="short")


def test_approval_commit_reachable_ok(tmp_path):
    repo = _tmp_git(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    verify_approval_commit_reachable(head, git_root=repo)


def test_approval_commit_dangling_rejected(tmp_path):
    repo = _tmp_git(tmp_path)
    c0 = _git(repo, "rev-parse", "HEAD")
    # create an unrelated commit: c0 is an object but not an ancestor of HEAD
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--orphan", "other"], check=True)
    subprocess.run(["git", "-C", str(repo), "rm", "-rf", "-q", "."], check=True)
    (repo / "other.txt").write_text("y", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "other"], check=True)
    with pytest.raises(ValueError, match="not reachable"):
        verify_approval_commit_reachable(c0, git_root=repo)


def test_approval_commit_missing_rejected(tmp_path):
    repo = _tmp_git(tmp_path)
    with pytest.raises(ValueError, match="not an existing"):
        verify_approval_commit_reachable("0" * 40, git_root=repo)