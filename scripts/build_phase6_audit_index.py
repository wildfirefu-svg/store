"""Phase 6 审计索引构建：把 .tmp 原始证据持久化进 docs/phase6/<run_id>/ 并生成哈希索引。

评审收口（6A0 CONDITIONAL_COMPLETE 项 2）：归档目录原本只有报告/summary/顶层 manifest，
240 条 detail、260 条事件、13 个 slice manifest 只在 .tmp——清理后无法复算与配对验证。
本脚本将每个切片的 detail/events/manifest/case_ids/summary 与预算账本复制到
docs/phase6/<run_id>/evidence/，逐文件记录 SHA-256（复制后重哈希校验一致），
并从原始 detail 行**独立复算**两臂每轮正确数与 Δ（不抄 summary.json），
同时补记 enriched dataset、config.py、claude_api.py 的 SHA-256 到归档 manifest。

用法：python scripts/build_phase6_audit_index.py --run-id 6a0-2024-001 --year 2024
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SLICE_FILES = ("detail.jsonl", "detail.events.jsonl", "detail.manifest.json",
               "case_ids.json", "summary.json")
EVIDENCE_NOTE = "config.py/claude_api.py 为实验时工作区内容（与提交 7c2707f 一致，实验后未改）"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def collect_run(root: Path, run_id: str, year: int) -> dict:
    """汇总运行实况：切片文件、detail 行、事件、预算账本、数据集。"""
    slices = []
    detail_rows: list[dict] = []
    events: list[dict] = []
    for arm in ("ctx_approved", "ctx_legacy"):
        runs_dir = root / arm / "runs" / run_id
        if not runs_dir.exists():
            continue
        for slice_dir in sorted(runs_dir.glob("slice_*")):
            entry = {"slice_id": slice_dir.name, "arm": arm,
                     "source_dir": str(slice_dir), "files": {}}
            for name in SLICE_FILES:
                p = slice_dir / name
                if p.exists():
                    entry["files"][name] = {"sha256": sha256_file(p),
                                            "bytes": p.stat().st_size}
            detail_rows.extend(_read_jsonl(slice_dir / "detail.jsonl"))
            events.extend(_read_jsonl(slice_dir / "detail.events.jsonl"))
            slices.append(entry)
    ledger_path = root / "budget" / f"{run_id}.jsonl"
    dataset_path = root / "datasets" / f"baziqa_contest8_{year}_holdout_enriched.jsonl"
    return {"slices": slices, "detail_rows": detail_rows, "events": events,
            "ledger_path": ledger_path, "dataset_path": dataset_path}


def recompute_accuracy(detail_rows: list[dict], repeats: int = 3) -> dict:
    """从原始 detail 行独立复算两臂每轮正确数/准确率与 Δ（attempt_key[2]=臂, [7]=repeat）。"""
    per_arm: dict = {}
    for arm in ("ctx_approved", "ctx_legacy"):
        per_repeat = []
        for rep in range(repeats):
            sel = [r for r in detail_rows
                   if (r.get("attempt_key") or [None] * 8)[2] == arm
                   and (r.get("attempt_key") or [None] * 8)[7] == rep]
            correct = sum(1 for r in sel if r.get("correct"))
            per_repeat.append({"repeat": rep, "correct": correct, "total": len(sel),
                               "accuracy": round(correct / len(sel), 4) if sel else None})
        per_arm[arm] = per_repeat
    deltas = [round((per_arm["ctx_approved"][r]["accuracy"]
                     - per_arm["ctx_legacy"][r]["accuracy"]) * 100, 2)
              for r in range(repeats)]
    return {"per_arm": per_arm, "per_repeat_delta_pp": deltas,
            "delta_dev_pp": round(sum(deltas) / len(deltas), 2)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 审计索引构建与证据持久化")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    args = parser.parse_args(argv)

    run = collect_run(args.root, args.run_id, args.year)
    if not run["slices"]:
        print(f"未找到运行切片: {args.root}/*/runs/{args.run_id}/slice_*")
        return 1

    out_dir = PROJECT_ROOT / "docs" / "phase6" / args.run_id
    evidence_dir = out_dir / "evidence"
    # 1) 持久化原始证据并校验复制完整性
    evidence_files = []
    for entry in run["slices"]:
        dest_dir = evidence_dir / entry["arm"] / entry["slice_id"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name, meta in entry["files"].items():
            src = Path(entry["source_dir"]) / name
            dest = dest_dir / name
            shutil.copy2(src, dest)
            copied = sha256_file(dest)
            if copied != meta["sha256"]:
                print(f"复制校验失败: {dest}")
                return 1
            evidence_files.append({"path": str(dest.relative_to(out_dir)),
                                   "sha256": meta["sha256"], "bytes": meta["bytes"]})
    ledger = {}
    if run["ledger_path"].exists():
        dest = evidence_dir / "budget_ledger.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run["ledger_path"], dest)
        ledger = {"path": str(dest.relative_to(out_dir)), "sha256": sha256_file(dest)}
    dataset_sha = sha256_file(run["dataset_path"]) if run["dataset_path"].exists() else None
    dataset_rows = len(_read_jsonl(run["dataset_path"])) if run["dataset_path"].exists() else 0

    # 2) 独立复算准确率与事件统计
    acc = recompute_accuracy(run["detail_rows"])
    terminal = Counter(r.get("terminal_state") for r in run["detail_rows"])
    event_kinds = Counter(e.get("kind") for e in run["events"])

    # 3) 审计索引
    index = {
        "run_id": args.run_id, "year": args.year,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generator": "scripts/build_phase6_audit_index.py",
        "enriched_dataset": {"path": str(run["dataset_path"]), "sha256": dataset_sha,
                             "rows": dataset_rows},
        "code": {"config.py": sha256_file(PROJECT_ROOT / "config.py"),
                 "claude_api.py": sha256_file(PROJECT_ROOT / "claude_api.py"),
                 "note": EVIDENCE_NOTE},
        "slices": [{**{k: e[k] for k in ("slice_id", "arm")}, "files": e["files"]}
                   for e in run["slices"]],
        "evidence_files": evidence_files,
        "budget_ledger": ledger,
        "totals": {
            "detail_rows": len(run["detail_rows"]),
            "terminal_state": dict(terminal),
            "call_attempt_events": event_kinds.get("call_attempt", 0),
            "model_call_failed_events": event_kinds.get("model_call_failed", 0),
        },
        "accuracy_recomputed": acc,
    }
    (out_dir / "audit_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) 归档 manifest 补记（保留原有字段）
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) \
        if manifest_path.exists() else {"run_id": args.run_id}
    manifest.update({
        "dataset_sha256": dataset_sha,
        "config_py_sha256": index["code"]["config.py"],
        "claude_api_py_sha256": index["code"]["claude_api.py"],
        "code_scope_note": ("切片 manifest 的 code_sha256 为实验时 6 文件 scope；"
                            "config.py/claude_api.py 于评审收口补录（提交 8ca46ac 起纳入 scope）"),
        "audit_index": "audit_index.json",
        "evidence_dir": "evidence/",
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(json.dumps({"status": "OK", "slices": len(run["slices"]),
                      "evidence_files": len(evidence_files),
                      "delta_dev_pp": acc["delta_dev_pp"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
