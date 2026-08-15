"""CLI verifier for the final-anchor receipt (stage 8)."""
from __future__ import annotations
import argparse, json, hashlib, subprocess
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.classic_artifacts import (
    EXPERIMENT_ID, generation_index_sha256, _git, _try_git_show,
    verify_batch_anchors, verify_generation_index_entries, repository_identity,
)
_FINAL_ANCHOR_FIELDS = ("schema_version", "final_commit", "generation_index_head_sha256", "final_audit_receipt_sha256", "approver", "approved_at", "batch_count", "last_batch_anchor_sha256", "experiment_id", "repository_identity")

def _git_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def build_final_anchor_receipt(*, final_commit, generation_index_head_sha256, final_audit_receipt_sha256, approver, approved_at, batch_count, last_batch_anchor_sha256, experiment_id, repository_identity):
    return {"schema_version": "1.0", "final_commit": final_commit, "generation_index_head_sha256": generation_index_head_sha256, "final_audit_receipt_sha256": final_audit_receipt_sha256, "approver": approver, "approved_at": approved_at, "batch_count": batch_count, "last_batch_anchor_sha256": last_batch_anchor_sha256, "experiment_id": experiment_id, "repository_identity": repository_identity}

def verify_final_anchor(receipt_path, *, index_rel, audit_rel, genesis_anchor, git_root, anchors_path):
    rec = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    for k in _FINAL_ANCHOR_FIELDS:
        if k not in rec: raise ValueError(f"final anchor receipt missing {k}")
    if rec["experiment_id"] != EXPERIMENT_ID: raise ValueError("final anchor experiment_id mismatch with frozen EXPERIMENT_ID")
    repo_id = repository_identity(git_root)
    if rec["repository_identity"] != repo_id: raise ValueError("final anchor repository_identity mismatch with current repository")
    final_commit = rec["final_commit"]
    if _git(git_root, "cat-file", "-e", f"{final_commit}^{{commit}}").returncode != 0: raise ValueError("final_commit not an existing reachable commit")
    anchors = json.loads(Path(anchors_path).read_text(encoding="utf-8"))
    if not isinstance(anchors, list) or not anchors: raise ValueError("final anchor anchors must be a non-empty list")
    if not verify_batch_anchors(anchors, git_root, genesis_commit=genesis_anchor, final_commit=final_commit): raise ValueError("final anchor batch anchor chain verification failed")
    blob = _try_git_show(git_root, final_commit, index_rel)
    if blob is None: raise ValueError(f"index blob missing at {final_commit}:{index_rel}")
    entries = json.loads(blob.decode("utf-8")) if blob else []
    if not verify_generation_index_entries(entries, genesis_anchor, rec["generation_index_head_sha256"]): raise ValueError("final anchor index chain verification failed")
    if len(entries) != rec["batch_count"]: raise ValueError(f"final anchor batch_count {rec['batch_count']} != index entries {len(entries)}")
    if _git_sha256(anchors[-1]) != rec["last_batch_anchor_sha256"]: raise ValueError("final anchor last batch anchor SHA mismatch")
    audit_blob = _try_git_show(git_root, final_commit, audit_rel)
    if audit_blob is None: raise ValueError(f"audit blob missing at {final_commit}:{audit_rel}")
    if hashlib.sha256(audit_blob).hexdigest() != rec["final_audit_receipt_sha256"]: raise ValueError("final anchor audit receipt SHA mismatch")
    if not rec.get("approver") or not rec.get("approved_at"): raise ValueError("final anchor missing approver/approved_at")
    return True

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-anchor", required=True); ap.add_argument("--index-rel", required=True); ap.add_argument("--audit-rel", required=True); ap.add_argument("--git-root", required=True); ap.add_argument("--genesis", required=True); ap.add_argument("--anchors", required=True)
    a = ap.parse_args(argv)
    verify_final_anchor(a.final_anchor, index_rel=a.index_rel, audit_rel=a.audit_rel, genesis_anchor=a.genesis, git_root=a.git_root, anchors_path=a.anchors)
    print("final anchor verified"); return 0

if __name__ == "__main__": raise SystemExit(main())