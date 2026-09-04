"""Generate a historical-artifact exemption request (E) for a classic-text book.

E is the executor's deliverable in the E -> R -> B1 approval chain. The
executor NEVER writes the approval receipt (R) -- that is the approver's
action. See scripts/classic_artifacts.py for the exemption schema and
verification.

v1 (--schema-version 1.0, default): legacy request, path unchanged.
v2 (--schema-version 2.0): design §6 12-field request; artifact/validator
SHAs come from the §5-E2 Git-object authoritative recompute at the frozen
base, and the freeze/evidence file SHAs bind the historical chain.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.classic_artifacts import (
    BASE_COMMIT,
    V2_BOOKS,
    build_artifact_manifest,
    recompute_artifact_manifest_sha256,
    recompute_validator_code_sha256,
    verify_exemption_request,
)

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True); ap.add_argument("--baseline", required=True); ap.add_argument("--out", required=True); ap.add_argument("--git-root", default=str(ROOT))
    ap.add_argument("--schema-version", default="1.0", choices=("1.0", "2.0"))
    ap.add_argument("--freeze"); ap.add_argument("--evidence")
    ap.add_argument("--author", default="implementing-agent"); ap.add_argument("--date", default="2026-09-04")
    a = ap.parse_args(argv)
    git_root = Path(a.git_root)
    if a.schema_version == "2.0":
        if a.book not in V2_BOOKS:
            print(f"unknown book {a.book!r}; must be one of {V2_BOOKS}", file=sys.stderr); return 1
        if a.baseline != BASE_COMMIT:
            print(f"v2 baseline_commit must equal the frozen base {BASE_COMMIT}", file=sys.stderr); return 1
        if not a.freeze or not a.evidence:
            ap.error("--freeze and --evidence are required with --schema-version 2.0")
        manifest_sha = recompute_artifact_manifest_sha256(git_root, a.baseline, a.book)
        val_sha = recompute_validator_code_sha256(git_root, a.baseline)
        freeze_sha = hashlib.sha256(Path(a.freeze).read_bytes()).hexdigest()
        evidence_sha = hashlib.sha256(Path(a.evidence).read_bytes()).hexdigest()
        parent = subprocess.run(["git", "-C", str(git_root), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        if not (len(parent) == 40 and all(c in "0123456789abcdef" for c in parent)):
            print("cannot resolve HEAD to a 40-hex commit", file=sys.stderr); return 1
        e = {"schema_version": "2.0", "book": a.book, "artifact_manifest_sha256": manifest_sha, "baseline_commit": a.baseline, "validator_code_sha256": val_sha, "historical_record_freeze_sha256": freeze_sha, "historical_generation_evidence_sha256": evidence_sha, "exempted_checks": ["missing_formal_model_run_manifest"], "non_exempt_checks": ["artifact_integrity", "quality_gates", "future_generation_provenance"], "author": a.author, "date": a.date, "parent_commit": parent}
    else:
        book_dir = git_root / "knowledge_base" / "classic_texts" / a.book
        man = build_artifact_manifest(book_dir, git_ref=a.baseline, git_root=git_root)
        manifest_sha = hashlib.sha256(json.dumps(man, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        val_sha = hashlib.sha256((git_root / "scripts/validate_classic_distillation.py").read_bytes()).hexdigest()
        e = {"schema_version": "1.0", "book": a.book, "baseline_commit": a.baseline, "artifact_manifest_sha256": manifest_sha, "validator_code_sha256": val_sha, "exempted_checks": ["missing_upstream_response_body"], "non_exempt_checks": ["artifact_integrity", "quality_gates", "future_generation_provenance"], "author": "implementing-agent", "date": "2026-08-13", "reason": "80 章为历史导入无上游 response body，豁免缺失上游链；内容完整性与质量门不豁免"}
    verify_exemption_request(e)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    # 纯 LF 二进制写出：指针 e_sha256 绑定 blob 字节，磁盘必须与提交 blob 逐字节一致
    # （write_text 在 Windows 下会把换行翻译为 CRLF，导致磁盘/blob 分裂）
    Path(a.out).write_bytes((json.dumps(e, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0

if __name__ == "__main__": raise SystemExit(main())