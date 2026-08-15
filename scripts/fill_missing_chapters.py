from __future__ import annotations
import json, os, re, shutil, hashlib, time
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import distill_lib as dl
import scripts.remediate_classic_distillation as rc
from scripts.distill_lib import _atomic_write_json, EXPERIMENT_ID, sha256_file, sha256_bytes
from scripts.fetch_sanming_chapters import materialization_status, _file_sha256

BASE = ROOT / "knowledge_base" / "classic_texts"
_RECEIPT_OUTPUT_NAMES = ("all_rules.json", "all_mcq.jsonl", "quarantine_mcq.jsonl", "remediation_meta.json", "progress.json")

def load_existing_rule_ids(dir_key: str) -> list[str]:
    p = BASE / dir_key / "all_rules.json"
    if not p.exists(): return []
    return sorted(r.get("id", "") for r in json.loads(p.read_text(encoding="utf-8")) if r.get("id"))

def _output_shas(out_dir: Path) -> dict:
    return {name: sha256_file(out_dir / name) for name in _RECEIPT_OUTPUT_NAMES if (out_dir / name).exists()}

def _seed_staging_from_existing(staging: Path, out_dir: Path) -> None:
    for name in _RECEIPT_OUTPUT_NAMES:
        src = out_dir / name
        if src.exists(): shutil.copy2(src, staging / name)

def _append_rules(staging: Path, rules: list[dict]) -> None:
    p = staging / "all_rules.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    data.extend(rules); p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _append_mcqs(staging: Path, mcqs: list[dict], quarantine: bool = False) -> None:
    name = "quarantine_mcq.jsonl" if quarantine else "all_mcq.jsonl"
    with (staging / name).open("a", encoding="utf-8") as f:
        for m in mcqs: f.write(json.dumps(m, ensure_ascii=False) + "\n")

def _segment_manifest_sha(segs_by_chapter: dict) -> str:
    canon = json.dumps([{"chapter": ch, "segs": [(s.char_start, s.char_end) for s in segs]} for ch, segs in sorted(segs_by_chapter.items())], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_bytes(canon.encode("utf-8"))

def _model_prompt_config_sha() -> str:
    canon = dl.RULE_PROMPT + "\0" + dl.PER_RULE_MCQ_PROMPT + "\0" + dl.MCQ_PROMPT + f"\0{dl.MAX_PROMPT_CHARS}:{dl.MAX_REQUEST_BYTES}"
    return sha256_bytes(canon.encode("utf-8"))

def _code_sha_now(scripts_dir: Path, root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(dl.ledger_code_files(scripts_dir, root)): h.update(f.read_bytes()); h.update(b"\0")
    return h.hexdigest()

def _git(git_root: Path, *args):
    import subprocess as _sp; return _sp.run(["git", "-C", str(git_root), *args], capture_output=True, text=True)

def _validate_manifest_bindings(m, *, snapshot_dir, out_dir, scripts_dir, root, git_root):
    if m["experiment_id"] != EXPERIMENT_ID: raise ValueError(f"experiment_id mismatch: {m['experiment_id']}")
    for ch in m["selected_chapter_ids"]:
        src = snapshot_dir / f"raw_{ch:03d}.txt"
        if not src.exists(): raise ValueError(f"missing raw for chapter {ch}")
        if sha256_file(src) != m["source_sha_map"].get(str(ch)): raise ValueError(f"source_sha_map mismatch for chapter {ch}")
    if sha256_bytes(json.dumps(_output_shas(out_dir), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) != m["pre_run_output_sha"]: raise ValueError("pre_run_output_sha mismatch")
    r = _git(git_root, "rev-parse", "HEAD")
    if r.returncode != 0 or r.stdout.strip() != m["parent_head_sha"]: raise ValueError("parent_head_sha != git HEAD")
    if _git(git_root, "cat-file", "-e", m["parent_commit"]).returncode != 0: raise ValueError("parent_commit not an existing commit")
    if _code_sha_now(scripts_dir, root) != m["code_sha"]: raise ValueError("code_sha drift vs manifest")

def _validate_snapshot_bindings(m, *, formal_dir, snapshot_dir, snapshot_sha):
    act = json.loads((formal_dir / "active_source_snapshot.json").read_text(encoding="utf-8")) if (formal_dir / "active_source_snapshot.json").exists() else None
    if not act or not act.get("snapshot_sha256") or not act.get("source_manifest_sha256"): raise ValueError("active_source_snapshot.json incomplete")
    if act["snapshot_sha256"] != m["source_snapshot_sha256"]: raise ValueError("active pointer snapshot_sha256 != manifest.source_snapshot_sha256")
    if snapshot_sha != m["source_snapshot_sha256"]: raise ValueError("snapshot_sha param != manifest.source_snapshot_sha256")
    snap_dir = formal_dir / "source_snapshots" / m["source_snapshot_sha256"]
    if not snap_dir.is_dir(): raise ValueError(f"snapshot dir missing: {snap_dir}")
    if _file_sha256(snap_dir / "source_manifest.json") != act["source_manifest_sha256"]: raise ValueError("active pointer source_manifest_sha256 != actual manifest file bytes SHA")
    if _file_sha256(snap_dir / "source_manifest.json") != m["source_manifest_sha256"]: raise ValueError("actual manifest file bytes SHA != manifest.source_manifest_sha256")
    if _file_sha256(snap_dir / "RESPONSE_ARCHIVE_POINTER.json") != m["source_archive_pointer_sha256"]: raise ValueError("source_archive_pointer_sha256 mismatch")
    if snapshot_dir.resolve() != (snap_dir / "extracted").resolve(): raise ValueError("snapshot_dir does not resolve to frozen snapshot extracted/ dir")

def _write_receipt(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); _atomic_write_json(path, obj)

def _rollback_staging(staging: Path) -> None:
    if staging.exists(): shutil.rmtree(staging, ignore_errors=True)

_BACKUP_DIR_RE = re.compile(r"^\.publish_backup_\d+_\d+$")

def _backup_fingerprint(backup_dir: Path) -> dict:
    """P0-3：备份目录内容指纹——成员集 SHA + 各成员内容 SHA 映射 SHA。

    用于把 backup 目录绑定到本 batch：发布时冻结进 completed receipt（收进 completed_receipt_sha256 被 index 认证），
    cleanup 删除前必须与已认证 receipt 冻结的指纹一致，否则合法目录名但属于另一 batch 的备份也会被拒绝。
    """
    if not backup_dir.is_dir():
        return {"member_set_sha256": None, "member_shas_sha256": None, "member_count": 0}
    names = sorted(p.name for p in backup_dir.iterdir())
    member_set_sha = sha256_bytes(json.dumps(names, ensure_ascii=False).encode("utf-8"))
    member_shas = {p.name: sha256_file(p) for p in backup_dir.iterdir() if p.is_file()}
    member_shas_sha = sha256_bytes(json.dumps(member_shas, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return {"member_set_sha256": member_set_sha, "member_shas_sha256": member_shas_sha, "member_count": len(names)}

def _retry_pending_cleanup(receipt_dir: Path, out_dir: Path, *, batch_id: str, genesis_anchor: str,
                           frozen_backup_dir: Path | None, frozen_fingerprint: dict | None) -> str:
    """P0-3：completed_idempotent 入口重试未完成的 cleanup——只删除"已认证 completed receipt 冻结"的备份目录。

    返回清理状态（fail-closed，任何身份/路径/指纹/解析/文件系统失败都不吞掉、不进入 completed_idempotent）：
    - "noop"：无 cleanup_pending（无需清理）；
    - "cleaned"：pending 存在且清理完成（备份已删除 / 或删除目标已不存在），pending 标记已清除；
    - "blocked"：身份/路径/指纹/解析/文件系统失败——pending 与备份目录均保留，调用方必须返回
      completed_cleanup_blocked 而非 completed_idempotent（含 rmtree 部分删除后失败：指纹将不再匹配，
      不可被静默吞成 completed）。

    安全约束（防 cleanup_pending.json 驱动的任意目录递归删除 / 跨 batch 删除）：
    1. 仅在 completed receipt 被 generation index 认证之后调用（bytes SHA == 索引 entry，
       backup_dir/backup_fingerprint 因此收进 completed_receipt_sha256；篡改任何字段都会使索引匹配失败 -> fail-closed）；
    2. cleanup_pending.json 必须匹配本 batch 的 batch_id 与 genesis_commit，否则 blocked（防御性复核）；
    3. 删除目标 = completed receipt 冻结的 frozen_backup_dir（不信任可变 cleanup_pending 的 backup_dir 字段）；
    4. 路径解析为绝对路径，必须严格位于 out_dir 内且目录名匹配确定性模式 .publish_backup_<pid>_<ts>；
    5. 磁盘上的内容指纹（成员集 SHA + 成员内容 SHA 映射）必须与冻结的 frozen_fingerprint 一致，
       否则视为"合法目录名但属于另一 batch 的备份"，blocked；
    6. 全部通过才 rmtree；成功才清除 pending 标记。任何失败返回 blocked 并保留 pending。
    """
    cp = receipt_dir / "cleanup_pending.json"
    if not cp.exists(): return "noop"
    if frozen_backup_dir is None or frozen_fingerprint is None: return "blocked"   # 无可认证删除目标
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
    except Exception:
        return "blocked"   # pending 解析失败，保留 pending
    if data.get("batch_id") != batch_id or data.get("genesis_commit") != genesis_anchor: return "blocked"   # 错误 batch
    try:
        resolved = Path(frozen_backup_dir).resolve()
        root = out_dir.resolve()
        try: rel = resolved.relative_to(root)
        except ValueError: return "blocked"   # 逃逸出 backup root
        if ".." in rel.parts or not _BACKUP_DIR_RE.fullmatch(rel.name): return "blocked"   # 非确定性目录名
    except Exception:
        return "blocked"
    if not resolved.exists():
        cp.unlink(missing_ok=True); return "cleaned"   # 删除目标已不存在，本 batch 身份已对齐，清除 pending
    fp = _backup_fingerprint(resolved)
    if fp["member_set_sha256"] != frozen_fingerprint.get("member_set_sha256") or fp["member_shas_sha256"] != frozen_fingerprint.get("member_shas_sha256"):
        return "blocked"   # 内容指纹不匹配（可能是另一 batch 的备份）
    try:
        shutil.rmtree(resolved)
    except Exception:
        return "blocked"   # rmtree 失败（含部分删除）：保留 pending，调用方必须显式处理，不可静默成 completed
    cp.unlink(missing_ok=True)
    return "cleaned"


def _build_rule_id_map(old_rules, new_rules) -> dict:
    """P0-3 中优：把历史 progress 规则逐记录映射到当前 all_rules.json 规则。

    真实数据中旧 ID 不唯一（1727 条记录 / 92 个唯一旧 ID，smth_0001 出现 78 次），
    因此不能用 dict[old_id]（会被覆盖）。改为逐记录映射，并以 canonical_key 为发生身份：

    - mapped：old canonical_key 唯一对应一个 new_id；
    - conflicts：old canonical_key 对应多个不同 new_id（一对多，无法唯一确定）；
    - unmappable：缺 canonical 字段或 new 中无对应规则。

    返回 {mapped, conflicts, unmappable, mapped_sha256, conflicts_sha256, unmappable_sha256}，
    且 len(mapped) + len(conflicts) + len(unmappable) == len(old_rules)（逐记录守恒）。
    """
    new_by_key = {}
    for r in new_rules:
        try: k = r.get("canonical_key") or dl._canonical_key(r)
        except ValueError: continue
        new_by_key.setdefault(k, set()).add(r.get("id"))
    mapped, conflicts, unmappable = [], [], []
    for r in old_rules:
        oid = r.get("id")
        record = {"old_id": oid, "old_record_sha256": sha256_bytes(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))}
        try: k = dl._canonical_key(r)
        except ValueError:
            record["reason"] = "missing_canonical_field"; unmappable.append(record); continue
        nids = [i for i in (new_by_key.get(k) or set()) if i]
        record["canonical_key"] = k
        if not nids:
            record["reason"] = "no_new_rule"; unmappable.append(record)
        elif len(nids) == 1:
            record["new_id"] = nids[0]; mapped.append(record)
        else:
            record["new_ids"] = sorted(nids); conflicts.append(record)
    def _sha(items):
        return sha256_bytes(json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")) if items else None
    return {"mapped": mapped, "conflicts": conflicts, "unmappable": unmappable,
            "mapped_sha256": _sha(mapped), "conflicts_sha256": _sha(conflicts), "unmappable_sha256": _sha(unmappable)}

def _update_progress(staging: Path, *, run_id, batch_id, genesis_anchor, titles=None, selected_chapters=None):
    # P0-3：progress 内嵌数组由 staged outputs 重建，属于**受控 reconcile**（显式记录迁移），不是静默改写。
    # 真实数据中 progress.all_rules(1727)!=all_rules.json(1542)、ID 命名空间也不同（smth_0001 vs smth_000_000），
    # 因此必须在 remediation_meta 记录输入/输出 SHA、数量差异、逐条 ID 映射与不可映射清单。
    p = staging / "progress.json"
    prog = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    input_sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    titles = titles or {}; selected_chapters = selected_chapters or []
    done = set(prog.get("done", []))
    for ch in selected_chapters:
        done.add(titles.get(ch, str(ch)))
    done = sorted(done)
    rules_p = staging / "all_rules.json"
    rules = json.loads(rules_p.read_text(encoding="utf-8")) if rules_p.exists() else []
    mcq_p = staging / "all_mcq.jsonl"
    mcqs = [json.loads(l) for l in mcq_p.read_text(encoding="utf-8").splitlines()] if mcq_p.exists() else []
    old_counts = {"all_rules": len(prog.get("all_rules", [])), "all_mcqs": len(prog.get("all_mcqs", []))}
    # P0-3 中优：旧/新规则逐记录 ID 映射（旧 smth_0001 命名空间 -> 新 smth_000_000），按 canonical key 匹配
    recon = _build_rule_id_map(prog.get("all_rules", []), rules)
    prog.update({"run_id": run_id, "batch_id": batch_id, "status": "published", "genesis_commit": genesis_anchor, "updated_at": time.time(),
                 "done": done, "total_rules": len(rules), "total_mcqs": len(mcqs),
                 "all_rules": rules, "all_mcqs": mcqs})
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8"); os.replace(str(tmp), str(p))
    output_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    _record_progress_reconcile(staging, run_id=run_id, batch_id=batch_id, genesis_anchor=genesis_anchor,
                               input_sha=input_sha, output_sha=output_sha, old_counts=old_counts,
                               new_counts={"all_rules": len(rules), "all_mcqs": len(mcqs)},
                               mapped=recon["mapped"], mapped_sha256=recon["mapped_sha256"],
                               conflicts=recon["conflicts"], conflicts_sha256=recon["conflicts_sha256"],
                               unmappable=recon["unmappable"], unmappable_sha256=recon["unmappable_sha256"])

def _record_progress_reconcile(staging: Path, *, run_id, batch_id, genesis_anchor, input_sha, output_sha, old_counts, new_counts,
                               mapped=None, mapped_sha256=None, conflicts=None, conflicts_sha256=None,
                               unmappable=None, unmappable_sha256=None) -> None:
    """P0-3：把 progress 重建作为显式迁移记入 remediation_meta（输入/输出 SHA、数量差异、逐记录映射/冲突/不可映射清单）。"""
    p = staging / "remediation_meta.json"
    meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"actions": []}
    meta.setdefault("actions", []).append({"type": "progress_reconcile", "batch_id": batch_id, "run_id": run_id, "genesis_commit": genesis_anchor,
                                           "input_progress_sha256": input_sha, "output_progress_sha256": output_sha,
                                           "old_counts": old_counts, "new_counts": new_counts,
                                           "mapped": mapped or [], "mapped_sha256": mapped_sha256,
                                           "conflicts": conflicts or [], "conflicts_sha256": conflicts_sha256,
                                           "unmappable": unmappable or [], "unmappable_sha256": unmappable_sha256,
                                           "note": "progress 内嵌数组由当前 all_rules.json/all_mcq.jsonl 重建；历史 ID 命名空间 smth_0001 与现行 smth_000_000 的逐记录映射见 mapped（canonical key 匹配），一对多冲突见 conflicts，无法映射见 unmappable；mapped+conflicts+unmappable==old 记录数守恒"})
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def _update_remediation_meta(staging: Path, *, run_id, batch_id, chapters, genesis_anchor):
    p = staging / "remediation_meta.json"
    meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"actions": []}
    meta.setdefault("actions", []).append({"type": "distill_append", "batch_id": batch_id, "run_id": run_id, "chapters": chapters, "genesis_commit": genesis_anchor})
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def _backfill_staging_keys(staging: Path, *, run_id, batch_id, genesis_anchor) -> None:
    """P0-3：对 staging 中已 seed 的既有规则做原子 canonical key 补写，并写入 provenance receipt。"""
    p = staging / "all_rules.json"
    if not p.exists(): return
    input_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    rules = json.loads(p.read_text(encoding="utf-8"))
    id_set_sha = dl.sha256_bytes(json.dumps(sorted(r.get("id", "") for r in rules), ensure_ascii=False).encode("utf-8"))
    count = len(rules)
    dl.backfill_canonical_keys(staging)          # 原子补写（tmp + os.replace）
    output_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    meta = {"type": "canonical_key_backfill", "batch_id": batch_id, "run_id": run_id, "genesis_commit": genesis_anchor,
            "input_sha256": input_sha, "output_sha256": output_sha, "rules_count": count, "id_set_sha256": id_set_sha}
    rem_p = staging / "remediation_meta.json"
    rem = json.loads(rem_p.read_text(encoding="utf-8")) if rem_p.exists() else {"actions": []}
    rem.setdefault("actions", []).append(meta)
    rem_p.write_text(json.dumps(rem, ensure_ascii=False, indent=2), encoding="utf-8")

def run_sanming_batch(manifest_path: Path, *, snapshot_dir: Path, out_dir: Path, formal_dir: Path, snapshot_sha: str, proj_ledger_path: Path, run_ledger_path: Path, run_id: str, project_total_cap: int, scripts_dir: Path, root: Path, git_root: Path, genesis_anchor: str, limits=None, generation_index_path: Path | None = None) -> dict:
    m = dl.load_batch_manifest(manifest_path); batch_id = m["batch_id"]
    staging = out_dir / ".batch_staging" / batch_id; receipt_dir = out_dir / ".batch" / batch_id; backup_dir = None
    # P0-7/P0-8：已完成 batch 的幂等入口——先检查 completed receipt
    completed_receipt_path = receipt_dir / "completed_receipt.json"
    if completed_receipt_path.exists():
        rec = json.loads(completed_receipt_path.read_text(encoding="utf-8"))
        for k in ("batch_id", "status", "genesis_commit", "source_snapshot_sha256", "manifest_sha", "code_sha", "rules_sha", "run_id", "output_shas", "backup_dir", "backup_fingerprint"):
            if k not in rec: raise ValueError("completed receipt missing field (fail-closed, no re-call)")
        if rec.get("status") != "published": raise ValueError("completed receipt status not published (fail-closed, no re-call)")
        if (rec.get("batch_id") != batch_id or rec.get("genesis_commit") != genesis_anchor
                or rec.get("manifest_sha") != _file_sha256(manifest_path)
                or rec.get("source_snapshot_sha256") != m["source_snapshot_sha256"]
                or rec.get("code_sha") != m["code_sha"] or rec.get("rules_sha") != m["rules_sha"]
                or rec.get("run_id") != run_id): raise ValueError("completed receipt identity drift (fail-closed, no re-call)")
        if _output_shas(out_dir) != rec.get("output_shas"): raise ValueError("completed receipt output SHA mismatch (fail-closed, no re-call)")
        # P0-8：区分"已入 generation index"与"尚未 finalize"
        if generation_index_path is not None and Path(generation_index_path).exists():
            from scripts.classic_artifacts import GenerationIndex
            idx = GenerationIndex(Path(generation_index_path), genesis_anchor=genesis_anchor)
            if not idx.verify(): raise ValueError("generation index hash chain invalid (fail-closed, no re-call)")   # P0-4：验证完整链
            receipt_sha = hashlib.sha256(completed_receipt_path.read_bytes()).hexdigest()
            # P0-4/P0-1：idx.verify() 已校验完整 hash chain + entry schema（首条 previous=None、genesis_commit 40-hex）；
            # 此处只精确匹配 (batch_id, completed_receipt_sha256, genesis_commit)，不再手写 previous_index_sha256 长度条件
            matches = [e for e in idx._load() if e.get("batch_id") == batch_id and e.get("completed_receipt_sha256") == receipt_sha
                       and e.get("genesis_commit") == genesis_anchor]
            if matches:
                # P0-3：仅在此处（completed receipt 已被 index 认证：bytes SHA == 索引 entry）才重试 cleanup。
                # 备份目标与内容指纹取自已认证的 completed receipt（backup_dir/backup_fingerprint 已收进
                # completed_receipt_sha256），不信任可变的 cleanup_pending.json；指纹/路径不匹配即拒绝，绝不吞掉身份校验错误。
                cleanup_state = _retry_pending_cleanup(receipt_dir, out_dir, batch_id=batch_id, genesis_anchor=genesis_anchor,
                                                       frozen_backup_dir=Path(rec["backup_dir"]) if rec.get("backup_dir") else None,
                                                       frozen_fingerprint=rec.get("backup_fingerprint"))
                # P0-3：只允许"无 pending（noop）"或"清理成功（cleaned）"进入 completed_idempotent；
                # 身份/路径/指纹/解析/文件系统失败（blocked）-> completed_cleanup_blocked，pending 与备份目录保留。
                if cleanup_state == "blocked":
                    return {"status": "completed_cleanup_blocked", "batch_id": batch_id, "completed_receipt": str(completed_receipt_path)}
                return {"status": "completed_idempotent", "batch_id": batch_id, "completed_receipt": str(completed_receipt_path)}
            raise ValueError("completed receipt exists but generation index has no matching entry (fail-closed, no re-call)")
        # 未 finalize：completed receipt 尚未被 index 认证，不做 cleanup 重试（避免可变 pending/未认证 receipt 驱动的删除）
        return {"status": "published_pending_finalize", "batch_id": batch_id, "completed_receipt": str(completed_receipt_path)}
    published = False; backup_cleanup_pending = False
    try:
        if materialization_status(formal_dir, snapshot_sha) != "materialized": raise RuntimeError("snapshot unmaterialized: distillation requires materialized responses")
        _validate_snapshot_bindings(m, formal_dir=formal_dir, snapshot_dir=snapshot_dir, snapshot_sha=snapshot_sha)
        snap_dir_path = formal_dir / "source_snapshots" / m["source_snapshot_sha256"]
        src_man = json.loads((snap_dir_path / "source_manifest.json").read_text(encoding="utf-8"))
        titles = {c["chapter_index"]: c["title"] for c in src_man["chapters"]}   # P0-6：规范章节标题
        _validate_manifest_bindings(m, snapshot_dir=snapshot_dir, out_dir=out_dir, scripts_dir=scripts_dir, root=root, git_root=git_root)
        proj = dl.ProjectLedger.load_or_create(proj_ledger_path, experiment_id=EXPERIMENT_ID, total_cap=project_total_cap)
        run = dl.BudgetLedger.load_or_create(run_ledger_path, global_hard_cap=m["batch_hard_cap"], run_id=run_id, code_sha=m["code_sha"], rules_sha=m["rules_sha"])
        if staging.exists(): shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True); receipt_dir.mkdir(parents=True, exist_ok=True)
        _seed_staging_from_existing(staging, out_dir)
        _backfill_staging_keys(staging, run_id=run_id, batch_id=batch_id, genesis_anchor=genesis_anchor)   # P0-3：生产接线
        calls_before = run.calls_made; proj_before = proj.calls_made
        ctx = dl.BudgetCtx(run_id=run_id, batch_id=batch_id, proj=proj, run=run, proj_path=proj_ledger_path, run_path=run_ledger_path)
        segs_by_chapter = {}
        for ch_idx in m["selected_chapter_ids"]:
            src = snapshot_dir / f"raw_{ch_idx:03d}.txt"
            segs_by_chapter[ch_idx] = dl.segment_chapter(src.read_text(encoding="utf-8"), book="sanmingtonghui", chapter=str(ch_idx), limits=limits or dl.PromptLimits())
        if _segment_manifest_sha(segs_by_chapter) != m["segment_manifest_sha"]: raise ValueError("segment_manifest_sha mismatch")
        if _model_prompt_config_sha() != m["model_prompt_config_sha"]: raise ValueError("model_prompt_config_sha mismatch")
        rules_added = mcqs_added = quarantine_added = 0
        for ch_idx, segs in segs_by_chapter.items():
            ch0 = ch_idx - 1   # P0-5：ID 用 0-based ch_idx（章 81 -> smth_080_000）
            rules = dl.distill_segments(segs, book="sanmingtonghui", chapter=str(ch_idx), limits=limits or dl.PromptLimits(), ledger=run, budget_ctx=ctx, chapter_id=ch0)
            dl.dedup_then_assign_rule_ids(rules, "smth", ch0)
            mcqs_ok, mcqs_q = dl.generate_mcq(rules, "sanmingtonghui", str(ch_idx), ledger=run, budget_ctx=ctx, chapter_id=ch0)
            dl.assign_mcq_ids(mcqs_ok, "smth", ch0, 0); dl.assign_mcq_ids(mcqs_q, "smth", ch0, len(mcqs_ok))
            _append_rules(staging, rules); _append_mcqs(staging, mcqs_ok); _append_mcqs(staging, mcqs_q, quarantine=True)
            rules_added += len(rules); mcqs_added += len(mcqs_ok); quarantine_added += len(mcqs_q)
        _update_progress(staging, run_id=run_id, batch_id=batch_id, genesis_anchor=genesis_anchor, titles=titles, selected_chapters=m["selected_chapter_ids"])
        _update_remediation_meta(staging, run_id=run_id, batch_id=batch_id, chapters=m["selected_chapter_ids"], genesis_anchor=genesis_anchor)
        prepared = {"batch_id": batch_id, "status": "prepared", "manifest_sha": _file_sha256(manifest_path), "pre_run_output_sha": m["pre_run_output_sha"], "calls_made_before": calls_before, "proj_calls_made_before": proj_before, "staging_output_shas": _output_shas(staging)}
        _write_receipt(receipt_dir / "prepared_receipt.json", prepared)
        expected_staging_shas = _output_shas(staging)
        backup_dir = rc._publish(staging, out_dir, list(_RECEIPT_OUTPUT_NAMES))
        for name, sha in expected_staging_shas.items():
            if _file_sha256(out_dir / name) != sha: raise ValueError(f"publish verification failed for {name}")
        completed = {"batch_id": batch_id, "status": "published", "genesis_commit": genesis_anchor, "source_snapshot_sha256": m["source_snapshot_sha256"], "manifest_sha": _file_sha256(manifest_path), "code_sha": m["code_sha"], "rules_sha": m["rules_sha"], "run_id": run_id, "calls_made_after": run.calls_made, "output_shas": _output_shas(out_dir), "backup_dir": str(backup_dir) if backup_dir else None, "backup_fingerprint": _backup_fingerprint(backup_dir) if backup_dir else None}
        _write_receipt(receipt_dir / "completed_receipt.json", completed)
        published = True  # P0-6：进入不可回滚状态
        try:
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir)
                cp = receipt_dir / "cleanup_pending.json"
                if cp.exists(): cp.unlink(missing_ok=True)   # 中优：cleanup 完成即清除 pending 状态
                backup_dir = None
        except Exception:
            backup_cleanup_pending = True
            # P0-3：cleanup 状态持久化为独立 receipt（仅作标记；权威 backup_dir/内容指纹已在 completed receipt 冻结）
            _write_receipt(receipt_dir / "cleanup_pending.json", {"batch_id": batch_id, "status": "cleanup_pending", "genesis_commit": genesis_anchor, "backup_dir": str(backup_dir) if backup_dir else None})
        return {"status": "published", "batch_id": batch_id, "prepared_receipt": str(receipt_dir / "prepared_receipt.json"), "completed_receipt": str(receipt_dir / "completed_receipt.json"), "backup_cleanup_pending": backup_cleanup_pending}
    except Exception as e:
        if backup_dir is not None and not published:  # P0-6：published 后不再回滚
            rc._rollback_from_backup(out_dir, backup_dir, list(_RECEIPT_OUTPUT_NAMES))
        _rollback_staging(staging)
        verdict = dl.classify_failure_for_resume(e, code_sha_before=m["code_sha"], code_sha_now=_code_sha_now(scripts_dir, root))
        return {"status": verdict, "batch_id": batch_id, "error": repr(e), "prepared_receipt": str(receipt_dir / "prepared_receipt.json")}
