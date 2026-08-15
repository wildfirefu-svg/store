"""Run manifest for the E -> R -> B1 approval chain (stage 1).

A run manifest records which approval commit authorized a batch of runs.
verify_run_manifest enforces the schema and that approval_commit is a
40-char SHA; verify_approval_commit_reachable proves the commit object
exists and is reachable from HEAD (not dangling).
"""
from __future__ import annotations
import json, subprocess
from pathlib import Path

def build_run_manifest(*, run_id, approval_commit, schedule_hash="", raw_dataset_sha="", enriched_dataset_sha=""):
    return {"schema_version": "1.0", "run_id": run_id, "approval_commit": approval_commit, "schedule_hash": schedule_hash, "raw_dataset_sha": raw_dataset_sha, "enriched_dataset_sha": enriched_dataset_sha}

def verify_run_manifest(m, *, expected_approval_commit):
    for k in ("schema_version", "run_id", "approval_commit"):
        if k not in m: raise ValueError(f"run manifest missing {k}")
    if m["approval_commit"] != expected_approval_commit: raise ValueError("run manifest approval_commit mismatch")
    if len(m["approval_commit"]) != 40: raise ValueError("run manifest approval_commit not a 40-char commit")

def _git(git_root, *args):
    import subprocess as _sp; return _sp.run(["git", "-C", str(git_root), *args], capture_output=True, text=True)

def verify_approval_commit_reachable(commit, git_root):
    if _git(git_root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0: raise ValueError(f"approval_commit {commit} is not an existing commit object")
    if _git(git_root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0: raise ValueError(f"approval_commit {commit} is not reachable from HEAD (dangling)")