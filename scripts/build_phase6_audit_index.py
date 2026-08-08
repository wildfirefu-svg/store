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
ARCHIVE_ROOT = PROJECT_ROOT / "docs" / "phase6"        # v6 阻断 2：归档根目录

SLICE_FILES = ("detail.jsonl", "detail.events.jsonl", "detail.manifest.json",
               "case_ids.json", "summary.json")
EVIDENCE_NOTE = "config.py/claude_api.py 为实验时工作区内容（与提交 7c2707f 一致，实验后未改）"
TERMINAL_OK = frozenset(("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed"))


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


def collect_run(root: Path, run_id: str, year: int,
                arms: tuple = ("ctx_approved", "ctx_legacy")) -> dict:
    """汇总运行实况：切片文件、detail 行、事件、预算账本、数据集。"""
    slices = []
    detail_rows: list[dict] = []
    events: list[dict] = []
    for arm in arms:
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


def recompute_accuracy(detail_rows: list[dict],
                       arms: tuple = ("ctx_approved", "ctx_legacy"),
                       repeats: int = 3) -> dict:
    """从原始 detail 行独立复算两臂每轮正确数/准确率与 Δ（attempt_key[2]=臂, [7]=repeat）。"""
    per_arm: dict = {}
    for arm in arms:
        per_repeat = []
        for rep in range(repeats):
            sel = [r for r in detail_rows
                   if (r.get("attempt_key") or [None] * 8)[2] == arm
                   and (r.get("attempt_key") or [None] * 8)[7] == rep]
            correct = sum(1 for r in sel if r.get("correct"))
            per_repeat.append({"repeat": rep, "correct": correct, "total": len(sel),
                               "accuracy": round(correct / len(sel), 4) if sel else None})
        per_arm[arm] = per_repeat
    deltas = [round((per_arm[arms[0]][r]["accuracy"]
                     - per_arm[arms[1]][r]["accuracy"]) * 100, 2)
              for r in range(repeats)]
    return {"per_arm": per_arm, "per_repeat_delta_pp": deltas,
            "delta_dev_pp": round(sum(deltas) / len(deltas), 2)}


def _audit_validate_rows(detail_rows: list, expected_case_ids: list, repeats: int) -> None:
    """v4 高优 3 + v5 高优 6：审计脚本自己的最小完整性验证（不导入生产函数）。
    v5 新增：拒绝重复逻辑键 (case, repeat, sample_idx)（不只拒完全相同 attempt key）+
    断言精确行数 sample==600 / anchor==120 + 验证 sample stage==main、anchor stage==anchor。"""
    expected = set(expected_case_ids)
    seen_sample, seen_anchor, seen_keys = set(), set(), set()
    sample_count, anchor_count = 0, 0
    for r in detail_rows:
        ak = r.get("attempt_key") or [None] * 10
        key = tuple(ak)
        if key in seen_keys:
            raise ValueError(f"审计完整性：重复 attempt key {key}")
        seen_keys.add(key)
        cid = r.get("case_id")
        if cid not in expected:
            raise ValueError(f"审计完整性：预期外 case {cid}")
        arm = ak[2]
        stage = ak[3]                  # v5: ak[3]=attempt_stage
        rep = ak[7]
        idx = ak[8]
        terminal = r.get("terminal_state")
        if terminal not in TERMINAL_OK:
            raise ValueError(f"审计完整性：终态非法 {terminal}（{cid}）")
        if arm == "vote5_samples":
            if stage != "main":
                raise ValueError(f"审计完整性：sample stage 非 main：{stage}（{cid}）")
            if idx not in {0, 1, 2, 3, 4}:
                raise ValueError(f"审计完整性：sample_idx 越界 {idx}（{cid}）")
            logical = (cid, rep, idx)
            if logical in seen_sample:
                raise ValueError(f"审计完整性：重复逻辑键 {logical}（attempt key 不同）")
            seen_sample.add(logical)
            sample_count += 1
        elif arm == "anchor_single0":
            if stage != "anchor":
                raise ValueError(f"审计完整性：anchor stage 非 anchor：{stage}（{cid}）")
            if idx != 0:
                raise ValueError(f"审计完整性：anchor sample_idx 非 0（{cid}）")
            logical = (cid, rep)
            if logical in seen_anchor:
                raise ValueError(f"审计完整性：重复 anchor 逻辑键 {logical}")
            seen_anchor.add(logical)
            anchor_count += 1
        else:
            raise ValueError(f"审计完整性：未知 arm {arm}（{cid}）")
    exp_sample = {(c, r, i) for c in expected for r in range(repeats) for i in range(5)}
    exp_anchor = {(c, r) for c in expected for r in range(repeats)}
    if seen_sample != exp_sample:
        miss = len(exp_sample - seen_sample)
        extra = len(seen_sample - exp_sample)
        raise ValueError(f"审计完整性：sample 集合不匹配（缺失 {miss}，额外 {extra}）")
    if seen_anchor != exp_anchor:
        miss = len(exp_anchor - seen_anchor)
        extra = len(seen_anchor - exp_anchor)
        raise ValueError(f"审计完整性：anchor 集合不匹配（缺失 {miss}，额外 {extra}）")
    if sample_count != len(expected) * repeats * 5:
        raise ValueError(f"审计完整性：sample 行数 {sample_count} != {len(expected) * repeats * 5}")
    if anchor_count != len(expected) * repeats:
        raise ValueError(f"审计完整性：anchor 行数 {anchor_count} != {len(expected) * repeats}")


def recompute_vote_accuracy(detail_rows: list, expected_case_ids: list, repeats: int = 3) -> dict:
    """v3 阻断 1：题级投票复算 + 独立完整性检查（缺题/缺 anchor/重复 -> ValueError，不静默缩小分母）。
    v4 高优 3：完整性检查改用审计脚本自己的 _audit_validate_rows，不再导入生产 strict_rows_complete。

    按 (case, repeat) 聚合 5 样本 strict_majority，派生 vote5 / single@T(sample_idx=0) /
    anchor 三臂准确率与 Δ1/Δ2、unresolved。与 recompute_accuracy 的区别：后者按行统计
    （仅适用单样本臂），本函数按题级投票。"""
    _audit_validate_rows(detail_rows, expected_case_ids, repeats)
    from benchmark.runners.self_consistency import strict_majority
    acc = {"vote5": [], "single_t": [], "anchor": []}
    unresolved = 0
    for rep in range(repeats):
        cases = sorted(expected_case_ids)
        n_v5 = n_st = n_an = 0
        for cid in cases:
            srows = sorted((r for r in detail_rows
                            if r["case_id"] == cid
                            and (r.get("attempt_key") or [None] * 10)[2] == "vote5_samples"
                            and (r.get("attempt_key") or [None] * 10)[7] == rep),
                           key=lambda r: (r.get("attempt_key") or [None] * 10)[8])
            arow = next(r for r in detail_rows
                         if r["case_id"] == cid
                         and (r.get("attempt_key") or [None] * 10)[2] == "anchor_single0"
                         and (r.get("attempt_key") or [None] * 10)[7] == rep)
            votes = [r["predicted_answer"] if r.get("terminal_state") == "parsed" else None
                     for r in srows]
            v5 = strict_majority(votes)
            if v5 is None:
                unresolved += 1
            exp = srows[0]["expected_answer"]
            n_v5 += (v5 is not None and v5 == exp)
            n_st += (srows[0].get("terminal_state") == "parsed"
                     and srows[0]["predicted_answer"] == exp)
            n_an += bool(arow and arow.get("terminal_state") == "parsed"
                         and arow["predicted_answer"] == exp)
        n = len(cases) or 1
        acc["vote5"].append(round(n_v5 / n, 4))
        acc["single_t"].append(round(n_st / n, 4))
        acc["anchor"].append(round(n_an / n, 4))
    d1 = [round((a - b) * 100, 2) for a, b in zip(acc["vote5"], acc["single_t"])]
    d2 = [round((a - b) * 100, 2) for a, b in zip(acc["vote5"], acc["anchor"])]
    total = len(expected_case_ids) * repeats
    return {"acc": acc, "per_repeat_delta1": d1, "per_repeat_delta2": d2,
            "delta1_pp": round(sum(d1) / repeats, 2),
            "delta2_pp": round(sum(d2) / repeats, 2),
            "unresolved": unresolved,
            "unresolved_rate": round(unresolved / max(total, 1), 4)}


def check_summary_match(recomputed: dict, summary_path) -> bool:
    """v3 阻断 1：审计复算与归档 summary.json 自动比对。不一致返回 False（CLI 退出非零）。"""
    import json as _json
    from pathlib import Path as _Path
    s = _json.loads(_Path(summary_path).read_text(encoding="utf-8"))
    if abs(float(s.get("delta1_pp", 0)) - recomputed["delta1_pp"]) > 0.01:
        return False
    if abs(float(s.get("delta2_pp", 0)) - recomputed["delta2_pp"]) > 0.01:
        return False
    for arm in ("vote5", "single_t", "anchor"):
        sa = s.get("acc", {}).get(arm, [])
        ra = recomputed["acc"][arm]
        if len(sa) != len(ra) or any(abs(a - b) > 0.001 for a, b in zip(sa, ra)):
            return False
    if abs(float(s.get("unresolved_rate", 0)) - recomputed["unresolved_rate"]) > 0.001:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 审计索引构建与证据持久化")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    parser.add_argument("--arms", default="ctx_approved,ctx_legacy")
    parser.add_argument("--mode", choices=["row", "vote"], default="row")
    parser.add_argument("--skip-summary-check", action="store_true",
                        help="仅诊断用：--mode vote 时跳过与归档 summary.json 的自动比对（正式命令禁止）")
    args = parser.parse_args(argv)

    arms = tuple(args.arms.split(","))
    run = collect_run(args.root, args.run_id, args.year, arms=arms)
    if not run["slices"]:
        print(f"未找到运行切片: {args.root}/*/runs/{args.run_id}/slice_*")
        return 1

    out_dir = ARCHIVE_ROOT / args.run_id
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
    summary_check = None
    if args.mode == "vote":
        # 决策 9 / v3 阻断 1：题级投票复算（非按行）；expected_case_ids 取 dataset 唯一 case ID
        expected_case_ids = sorted({str(r.get("case_id"))
                                    for r in _read_jsonl(run["dataset_path"])})
        acc = recompute_vote_accuracy(run["detail_rows"], expected_case_ids, repeats=3)
        # v4 阻断 1：--mode vote 默认必须与同目录 summary.json 比对，不一致或缺失 exit 2
        summary_path = out_dir / "summary.json"
        summary_status = "SKIPPED" if args.skip_summary_check else "FAIL"
        summary_sha = None
        if not args.skip_summary_check:
            if summary_path.exists():
                summary_sha = sha256_file(summary_path)
                if check_summary_match(acc, summary_path):
                    summary_status = "PASS"
        summary_check = {"status": summary_status, "summary_sha256": summary_sha,
                         "recomputed": {"delta1_pp": acc["delta1_pp"],
                                        "delta2_pp": acc["delta2_pp"]}}
    else:
        acc = recompute_accuracy(run["detail_rows"], arms=arms, repeats=3)
    terminal = Counter(r.get("terminal_state") for r in run["detail_rows"])
    event_kinds = Counter(e.get("kind") for e in run["events"])

    # 3) 审计索引
    index = {
        "run_id": args.run_id, "year": args.year,
        "mode": args.mode,
        "dataset_sha256": dataset_sha,
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
    if summary_check is not None:
        index["summary_check"] = summary_check
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
    if args.mode == "vote" and not args.skip_summary_check:
        # v4 阻断 1：审计索引已落盘（含 FAIL 状态），但不一致/缺失必须 exit 2
        if summary_check["status"] != "PASS":
            print(json.dumps({"status": "SUMMARY_MISMATCH",
                              "summary_check": summary_check}, ensure_ascii=False))
            return 2
    print(json.dumps({"status": "OK", "slices": len(run["slices"]),
                      "evidence_files": len(evidence_files),
                      "delta_dev_pp": acc.get("delta_dev_pp", acc.get("delta1_pp"))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
