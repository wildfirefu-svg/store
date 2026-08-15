"""Generate a historical-artifact exemption request (E) for a classic-text book.

E is the executor's deliverable in the E -> R -> B1 approval chain. The
executor NEVER writes the approval receipt (R) -- that is the approver's
action. See scripts/classic_artifacts.py for the exemption schema and
verification.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.classic_artifacts import build_artifact_manifest, verify_exemption_request

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True); ap.add_argument("--baseline", required=True); ap.add_argument("--out", required=True); ap.add_argument("--git-root", default=str(ROOT))
    a = ap.parse_args(argv)
    git_root = Path(a.git_root)
    book_dir = git_root / "knowledge_base" / "classic_texts" / a.book
    man = build_artifact_manifest(book_dir, git_ref=a.baseline, git_root=git_root)
    manifest_sha = hashlib.sha256(json.dumps(man, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    val_sha = hashlib.sha256((git_root / "scripts/validate_classic_distillation.py").read_bytes()).hexdigest()
    e = {"schema_version": "1.0", "book": a.book, "baseline_commit": a.baseline, "artifact_manifest_sha256": manifest_sha, "validator_code_sha256": val_sha, "exempted_checks": ["missing_upstream_response_body"], "non_exempt_checks": ["artifact_integrity", "quality_gates", "future_generation_provenance"], "author": "implementing-agent", "date": "2026-08-13", "reason": "80 章为历史导入无上游 response body，豁免缺失上游链；内容完整性与质量门不豁免"}
    verify_exemption_request(e)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__": raise SystemExit(main())