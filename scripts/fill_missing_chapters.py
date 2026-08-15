from __future__ import annotations
import json, os, re, shutil, hashlib, sys, time
from pathlib import Path
import scripts.distill_lib as dl
import scripts.remediate_classic_distillation as rc
from scripts.classic_artifacts import ConservationError, mcq_record_sha256, validate_provenance
from scripts.distill_lib import _atomic_write_json, EXPERIMENT_ID, sha256_file, sha256_bytes
from scripts.fetch_sanming_chapters import materialization_status, _file_sha256

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "knowledge_base" / "classic_texts"
SCRIPTS_DIR = Path(__file__).resolve().parent
_RECEIPT_OUTPUT_NAMES = ("all_rules.json", "all_mcq.jsonl", "quarantine_mcq.jsonl", "remediation_meta.json", "progress.json")
CN_NUM = "一二三四五六七八九十"
_LEDGER_CODE_FILES = dl.ledger_code_files(SCRIPTS_DIR, ROOT)

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

def _cn_to_int(s: str) -> int:
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _cn_to_int(s[1:])
    if s.endswith("十"):
        return _cn_to_int(s[:-1]) * 10
    if "十" in s:
        a, b = s.split("十")
        return _cn_to_int(a) * 10 + _cn_to_int(b)
    return CN_NUM.index(s) + 1 if s in CN_NUM else 0


def _split_by_titles(text: str, titles: list[str]) -> dict[str, str]:
    """Split text by known titles: find each title in text, extract until next title."""
    positions = []
    for t in titles:
        idx = text.find(t)
        if idx >= 0:
            positions.append((idx, t))
    positions.sort()
    chapters = {}
    for i, (idx, t) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        chapters[t] = text[idx:end].strip()
    return chapters


def split_zpzq(text: str, titles: list[str]) -> dict[str, str]:
    return _split_by_titles(text, titles)


def split_qtbj(text: str, titles: list[str]) -> dict[str, str]:
    return _split_by_titles(text, titles)


def fill_book(dir_key: str, global_budget: int = 5000,
              ledger_path: Path | None = None,
              git_root: Path | None = None,
              run_id: str = "",
              code_sha: str = "",
              rules_sha: str = "",
              manifest_path: Path | None = None) -> dict:
    if dir_key == "zipingzhenquan":
        name, prefix, book_name = "子平真诠", "zpzq", "子平真诠"
        full_raw = BASE / dir_key / "raw_full.txt"
        if not full_raw.exists():
            return {"book": name, "error": "raw_full.txt not found"}
        text = full_raw.read_text(encoding="utf-8")
        ch_list = (BASE / dir_key / "chapter_list.txt").read_text(encoding="utf-8").splitlines()
        wanted = []
        for line in ch_list:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\.\s*(.+)", line)
            if m:
                wanted.append(m.group(1).strip())
        chapters = split_zpzq(text, wanted)
    elif dir_key == "qiongtongbaojian":
        name, prefix, book_name = "穷通宝鉴", "qtbj", "穷通宝鉴"
        full_raw = BASE / dir_key / "raw_full.txt"
        if not full_raw.exists():
            return {"book": name, "error": "raw_full.txt not found"}
        text = full_raw.read_text(encoding="utf-8")
        sec_list = (BASE / dir_key / "section_list.txt").read_text(encoding="utf-8").splitlines()
        wanted = []
        for line in sec_list:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\.\s*(.+)", line)
            if m:
                wanted.append(m.group(1).strip())
        chapters = split_qtbj(text, wanted)
    else:
        return {"error": f"unsupported book {dir_key}"}

    prog = json.loads((BASE / dir_key / "progress.json").read_text(encoding="utf-8"))
    done = set(prog.get("done", []))

    # find missing
    missing = []
    for w in wanted:
        if w not in done and w in chapters:
            missing.append(w)
    print(f"[{name}] {len(missing)} missing chapters to fill", flush=True)

    # P0-4: nothing to fill -> skip. Do NOT publish (which would rewrite
    # provenance) and do NOT create an api_generation record attributing the
    # existing MCQs to this zero-call run.
    if not missing:
        print(f"[{name}] nothing to fill (all chapters present)")
        return {"book": name, "skipped": True, "missing": 0}

    # load existing
    rules_path = BASE / dir_key / "all_rules.json"
    mcq_path = BASE / dir_key / "all_mcq.jsonl"
    existing_rules = json.loads(rules_path.read_text(encoding="utf-8"))
    existing_mcqs = [json.loads(l) for l in mcq_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    # determine ch_idx offset (max existing chapter index + 1)
    ch_indices = []
    for r in existing_rules:
        rid = r.get("id", "")
        m = re.search(rf"^{prefix}_(\d{{3}})_", rid)
        if m:
            ch_indices.append(int(m.group(1)))
    next_ch_idx = max(ch_indices) + 1 if ch_indices else 0

    # determine mcq seq offset
    mcq_seqs = []
    for m in existing_mcqs:
        mid = m.get("id", "")
        mt = re.search(r"mcq_(\d{4})$", mid)
        if mt:
            mcq_seqs.append(int(mt.group(1)))
    next_mcq_seq = max(mcq_seqs) + 1 if mcq_seqs else 0

    # P0-1/P0-2: Run-level shared budget ledger with frozen global hard cap AND
    # a frozen run identity (run_id/code_sha/rules_sha) computed once at the
    # CLI level. All books in one run share one ledger file and budget; a
    # different run is rejected (fail-closed) rather than silently reusing the
    # old ledger's budget.
    ledger = dl.BudgetLedger.load_or_create(
        ledger_path, global_budget,
        run_id=run_id, code_sha=code_sha, rules_sha=rules_sha)
    # Medium: snapshot the SHARED ledger so api_generation records THIS book's
    # call delta, not the cross-book cumulative total.
    _calls_before = ledger.legacy_calls
    _accepted_before = ledger.accepted
    _skipped_before = ledger.skipped
    new_rules_total = []
    new_mcqs_total = []
    new_mcq_quarantine: list[dict] = []
    chapters_done: list[str] = []
    # P0-2: defer raw_*.txt writes until chapter is confirmed complete.
    # Previously raw_*.txt was written BEFORE the completeness check, so a
    # fail-closed run still left raw files on disk ("files NOT written" was
    # false). Now we buffer (ch_title -> ch_text) and write only on success.
    pending_raw_writes: list[tuple[int, str, str]] = []
    incomplete = False

    for ch_title in missing:
        ch_text = chapters[ch_title]
        print(f"  [{next_ch_idx}] {ch_title[:25]}...", flush=True)
        try:
            rules = dl.distill_chapter(ch_text, book_name, ch_title, ledger=ledger)
        except Exception as e:
            print(f"    DISTILL ERROR: {e}")
            rules = []
        dl.assign_rule_ids(rules, prefix, next_ch_idx)
        # P0-2: do NOT write raw_*.txt here -- defer until chapter confirmed complete.

        # P0-3: empty rules -> fail-closed. An empty result means either
        # distill_failed (API error) or parser_invalid (unparseable output).
        # Both are failures, not "chapter has zero rules". The chapter must
        # NOT be marked done, and raw/progress must NOT be written.
        if not rules:
            print(f"    EMPTY RULES for chapter '{ch_title}' -- marking incomplete "
                  f"(distill_failed or parser_invalid)")
            incomplete = True
            break

        try:
            verified, unaudited = dl.generate_mcq(
                rules, book_name, ch_title, ledger=ledger)
            linked, unlinked = dl.link_mcq_to_rules(verified, rules)
        except Exception as e:
            print(f"    MCQ ERROR: {e}")
            linked, unlinked, unaudited = [], [], []
        next_mcq_seq = dl.assign_mcq_ids(linked, prefix, next_ch_idx, next_mcq_seq)

        new_rules_total.extend(rules)
        new_mcqs_total.extend(linked)
        new_mcq_quarantine.extend(unlinked)
        new_mcq_quarantine.extend(unaudited)

        # P0-2: fail-closed checks -- do NOT mark chapter as done if incomplete
        if ledger.exhausted:
            print(f"    BUDGET EXHAUSTED after chapter '{ch_title}' -- stopping")
            incomplete = True
            break
        if len(linked) < len(rules):
            print(f"    INCOMPLETE: {len(linked)}/{len(rules)} MCQs verified -- marking incomplete")
            incomplete = True
            break

        # Chapter confirmed complete -- safe to schedule raw write.
        pending_raw_writes.append((next_ch_idx, ch_title, ch_text))
        chapters_done.append(ch_title)
        next_ch_idx += 1
        time.sleep(0.3)

    # P0-2: fail-closed -- do NOT write files or update progress if incomplete
    if incomplete:
        print(f"[{name}] FAIL-CLOSED: budget exhausted or MCQs incomplete.")
        print(f"  Ledger: {ledger.summary()}")
        print(f"  Chapters processed: {len(chapters_done)}/{len(missing)}")
        print(f"  Progress NOT updated, rules/MCQ/raw files NOT written.")
        return {"book": name, "error": "fail_closed",
                "ledger": ledger.summary(),
                "chapters_done": len(chapters_done),
                "chapters_missing": len(missing)}

    # All chapters succeeded -- now safe to publish. P0-2/P0-3: write all files
    # (raw + rules + mcq + quarantine + progress + provenance + meta) to a
    # staging dir, then publish TRANSACTIONALLY via the same backup + per-file
    # replace + rollback + SHA-verify path that remediation/regen use. A
    # mid-publish failure fully restores the previous state instead of leaving
    # a half-updated directory.
    book_dir = BASE / dir_key

    # P0-3 finalization: refresh meta and recompute provenance so it does not
    # go stale after the rules/MCQ/raw files are replaced.
    meta_path = book_dir / "remediation_meta.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["needs_mcq_regen"] = False
    meta["fill"] = {
        "added_rules": len(new_rules_total),
        "added_mcq": len(new_mcqs_total),
        "chapters": chapters_done,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_id": run_id,
    }

    raw_names = [f"raw_{ch_idx:03d}_{ch_title[:10]}.txt"
                 for ch_idx, ch_title, _ in pending_raw_writes]
    output_names = (
        "all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
        "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json",
        "progress.json",
    ) + tuple(raw_names)

    staging = book_dir / f".fill_staging_{os.getpid()}"
    staging.mkdir(parents=True, exist_ok=True)
    backup_dir: Path | None = None
    try:
        for ch_idx, ch_title, ch_text in pending_raw_writes:
            (staging / f"raw_{ch_idx:03d}_{ch_title[:10]}.txt").write_text(
                ch_text, encoding="utf-8")

        done.update(chapters_done)
        all_rules = existing_rules + new_rules_total
        all_mcqs = existing_mcqs + new_mcqs_total
        dl.rotate_answers(all_mcqs)

        (staging / "all_rules.json").write_text(
            json.dumps(all_rules, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "all_mcq.jsonl").write_text(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in all_mcqs),
            encoding="utf-8")
        # Copy unchanged quarantine_rules.jsonl into staging so provenance
        # file_shas cover the FULL output set.
        qr_src = book_dir / "quarantine_rules.jsonl"
        if qr_src.exists():
            shutil.copy2(qr_src, staging / "quarantine_rules.jsonl")
        if new_mcq_quarantine:
            q_f = book_dir / "quarantine_mcq.jsonl"
            existing_q = []
            if q_f.exists():
                existing_q = [json.loads(l) for l in q_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            new_q = [m for m in new_mcq_quarantine
                     if all(m.get("question") != x.get("question") for x in existing_q)]
            merged_q = existing_q + new_q
            (staging / "quarantine_mcq.jsonl").write_text(
                "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in merged_q),
                encoding="utf-8")
        else:
            q_src = book_dir / "quarantine_mcq.jsonl"
            if q_src.exists():
                shutil.copy2(q_src, staging / "quarantine_mcq.jsonl")
        prog["done"] = list(done)
        prog["total_rules"] = len(all_rules)
        prog["total_mcqs"] = len(all_mcqs)
        (staging / "progress.json").write_text(
            json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "remediation_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        provenance = rc._compute_provenance(
            staging, book_dir, meta, git_root=git_root, no_api=False)
        # P0-2/P0-4: bind the CURRENT MCQ output to THIS run's API generation
        # chain. rules_input_sha hashes the rules ACTUALLY sent to the model
        # this run (new_rules_total) -- NOT the pre-run all_rules.json. Also
        # record the final rules output SHA. If no new rules/MCQs and no API
        # calls happened, no api_generation record is created (nothing new to
        # attribute to this run).
        if new_mcqs_total or ledger.calls_made > 0:
            mcq_out = (staging / "all_mcq.jsonl").read_bytes()
            rules_input_payload = json.dumps(
                new_rules_total, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")
            rules_output = json.loads((staging / "all_rules.json").read_text(encoding="utf-8"))
            rules_output_payload = json.dumps(
                rules_output, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")
            provenance["api_generation"] = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "run_id": run_id,
                "code_sha": code_sha,
                "rules_sha": rules_sha,
                "rules_input_sha": hashlib.sha256(rules_input_payload).hexdigest(),
                # P0-4: persist the actual rule set sent to the model so the
                # validator can independently recompute rules_input_sha instead
                # of trusting a 64-char string.
                "rules_input_snapshot": new_rules_total,
                "rules_output_sha": hashlib.sha256(rules_output_payload).hexdigest(),
                "rules_added": len(new_rules_total),
                "mcq_output_sha": hashlib.sha256(mcq_out).hexdigest(),
                "mcq_output_bytes": len(mcq_out),
                # P0-4: prove WHICH MCQs this run generated via per-ID canonical
                # record hashes (not just id membership) so a reviewer can verify
                # that all_mcq.jsonl's attributed records came from this chain
                # and were not replaced / re-used from a prior run. fill preserves
                # pre-existing MCQs, so the generated ids must be disjoint from
                # the frozen pre-run id set (P0-3).
                "generated_mcq_sha256_by_id": {
                    m.get("id"): mcq_record_sha256(m)
                    for m in new_mcqs_total if isinstance(m, dict) and m.get("id")
                },
                # P0-8: pre-run MCQ id set MUST equal the value frozen in the
                # archived run manifest (provenance is not the source of truth).
                "pre_run_mcq_ids": dl.pre_run_mcq_ids(book_dir / "all_mcq.jsonl"),
                "operation": "fill",
                "preserves_existing_mcqs": True,
                "prompt_sha256": dl.canonical_prompt_sha256(),
                "config_sha256": dl.canonical_config_sha256(),
                "script_sha256": hashlib.sha256(
                    (SCRIPTS_DIR / "distill_lib.py").read_bytes()).hexdigest(),
                "provider": dl.FROZEN_MODEL_CONFIG["provider"],
                "model": dl.FROZEN_MODEL_CONFIG["model"],
                "thinking_mode": dl.FROZEN_MODEL_CONFIG["thinking_mode"],
                "temperature": dl.FROZEN_MODEL_CONFIG["temperature"],
                # Medium: per-book call deltas, not cross-book cumulative totals.
                "calls_made": ledger.legacy_calls - _calls_before,
                "accepted": ledger.accepted - _accepted_before,
                "skipped": ledger.skipped - _skipped_before,
                "verification_level": "partial",  # corrected below if manifest archived
                "completed": True,
            }
        # P0-3: archive the frozen run manifest (FULL file: identity + intent)
        # INTO provenance so run_id/code_sha/rules_sha have a persistent
        # cross-check even after main() clears the work-copy manifest + ledger.
        if manifest_path is not None and manifest_path.exists():
            try:
                _mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                provenance["run_manifest"] = _mdata
                provenance["run_manifest_sha256"] = _mdata.get("manifest_sha256", "")
                # Medium: with an archived manifest the identity can be
                # re-derived -> full verification.
                provenance["api_generation"]["verification_level"] = "full"
            except Exception:
                pass
        (staging / "provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")

        # P0-2: write the PREPARED receipt bound to the staging output SHAs
        # right before publish. If the process crashes between here and the
        # completed receipt in main(), a resume resolves this prepared state.
        if manifest_path is not None:
            dl.append_book_receipt(
                manifest_path, dir_key, "prepared",
                book_dir=staging, output_names=_RECEIPT_OUTPUT_NAMES)

        # Transactional publish with backup + rollback (P0-2).
        backup_dir = rc._publish(staging, book_dir, list(output_names))

        # P0-3/P0-x: re-validate provenance on the PUBLISHED state with the
        # REAL git_root (no gate bypass). New raw files added by fill are
        # anchored via provenance `raw_sources` derivation entries (see
        # _compute_provenance) so the baseline full-coverage gate is satisfied
        # honestly rather than disabled. Any post-publish failure -- validation
        # returning False OR raising -- rolls back from backup; only validation
        # success deletes the backup.
        try:
            prov_ok, prov_issues = validate_provenance(book_dir, SCRIPTS_DIR, git_root=git_root)
            if not prov_ok:
                raise ConservationError(
                    f"fill provenance validation failed after publish: "
                    f"{'; '.join(prov_issues)}")
            # Success: discard backup.
            shutil.rmtree(backup_dir, ignore_errors=True)
            backup_dir = None
        except BaseException as exc:
            if backup_dir is not None:
                try:
                    rc._rollback_after_failure(
                        book_dir, backup_dir, list(output_names), repr(exc))
                    backup_dir = None
                except Exception as rb:
                    raise ConservationError(
                        f"post-publish failure {exc!r}; rollback ALSO failed: {rb!r}; "
                        f"backup preserved at {backup_dir}"
                    ) from exc
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"[{name}] added {len(new_rules_total)} rules, {len(new_mcqs_total)} MCQ")
    print(f"  Ledger: {ledger.summary()}")
    return {"book": name, "added_rules": len(new_rules_total), "added_mcq": len(new_mcqs_total),
            "total_rules": len(all_rules), "total_mcq": len(all_mcqs),
            "ledger": ledger.summary()}


def _build_run_manifest(targets: list[str]) -> dict:
    """Build the canonical pre-run manifest (P0-1/P0-2/P0-4).

    Split into immutable vs mutable:
      - immutable: the run's INTENT -- ordered targets, frozen prompt/config
        SHA, and SHAs of inputs fill does NOT modify (raw_full.txt,
        chapter_list.txt, section_list.txt).
      - mutable: the pre-run state of files fill itself rewrites
        (progress.json, all_rules.json, all_mcq.jsonl) -- allowed to change on
        resume because the run modifies them.
    """
    immutable: dict = {
        "targets": list(targets),  # order-preserving: reordering changes identity
        "frozen_config_sha256": dl.canonical_config_sha256(),
        "frozen_prompt_sha256": dl.canonical_prompt_sha256(),
        "input_files": {},
    }
    mutable: dict = {}
    for k in targets:
        d = BASE / k
        imm_entry: dict = {}
        for fname in ("raw_full.txt", "chapter_list.txt", "section_list.txt"):
            f = d / fname
            if f.exists():
                raw = f.read_bytes()
                imm_entry[fname + "_sha256"] = hashlib.sha256(raw).hexdigest()
                imm_entry[fname + "_bytes"] = len(raw)
        mut_entry: dict = {}
        for fname in ("progress.json", "all_rules.json", "all_mcq.jsonl"):
            f = d / fname
            if f.exists():
                raw = f.read_bytes()
                mut_entry[fname + "_sha256"] = hashlib.sha256(raw).hexdigest()
                mut_entry[fname + "_bytes"] = len(raw)
        # P0-8: freeze the pre-run MCQ id set so the validator can prove no old
        # MCQ was retroactively claimed as generated (immutable intent).
        imm_entry["pre_run_mcq_ids"] = dl.pre_run_mcq_ids(d / "all_mcq.jsonl")
        # P0-9: freeze the operation/mode so the validator is driven by the
        # immutable intent, not the unauthenticated provenance flag.
        imm_entry["operation"] = "fill"
        imm_entry["preserves_existing_mcqs"] = True
        immutable["input_files"][k] = imm_entry
        mutable[k] = mut_entry
    return {"immutable": immutable, "mutable": mutable}


def _compute_run_bindings(targets: list[str],
                          manifest_path: Path | None = None) -> tuple[str, str, str, dict]:
    """Freeze (or reload) the immutable run manifest and return the run identity.

    When manifest_path is given, the identity comes from the frozen manifest
    (create if absent, reload+verify immutable intent if present). Without a
    path (tests), the identity is computed directly from the current manifest.
    Returns (run_id, code_sha, rules_sha, book_state).
    """
    manifest = _build_run_manifest(targets)
    if manifest_path is not None:
        return dl.freeze_run_manifest(
            manifest_path, manifest, _LEDGER_CODE_FILES, mutable_root=BASE)
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    run_id, code_sha, rules_sha = dl.compute_run_bindings(payload, _LEDGER_CODE_FILES)
    return run_id, code_sha, rules_sha, {}


def main() -> int:
    fill_targets = dl.VALID_TARGETS_BY_OPERATION["fill"]
    requested = sys.argv[1:]
    # P0: distinguish "no args" (default: all) from "invalid explicit args"
    # (fail-closed, return 2). A typo must never expand into a full API run.
    if not requested:
        targets = list(fill_targets)
    else:
        invalid = [t for t in requested if t not in fill_targets]
        if invalid:
            print(f"ERROR: invalid targets: {invalid}", flush=True)
            return 2
        targets = requested
    # Medium: duplicate targets would double-execute books but collapse to one
    # manifest key -- reject them outright.
    if len(targets) != len(set(targets)):
        print(f"ERROR: duplicate targets not allowed: {targets}", flush=True)
        return 2
    # P0-2: single shared ledger across ALL books in this CLI run, so the
    # total API budget is enforced run-wide (not per-book). The ledger is
    # persisted to a single file so crash-restart does not reset the budget.
    ledger_path = BASE / ".fill_ledger.json"
    # P0-1: freeze the immutable run manifest BEFORE any book is processed, so
    # a run that modifies its own inputs can still resume after a crash with
    # the same identity. Resume verifies the frozen immutable intent.
    manifest_path = BASE / ".fill_run_manifest.json"
    run_id, code_sha, rules_sha, book_state = _compute_run_bindings(targets, manifest_path)
    # P0-2: run only books still pending -- a completed book is NEVER re-run on
    # resume, regardless of the explicit targets in this argv.
    pending = [t for t in targets if book_state.get(t) != "completed"]
    # P0-2: non-zero exit code if ANY book fails (budget exhausted or incomplete).
    any_error = False
    for k in pending:
        r = fill_book(k, ledger_path=ledger_path, git_root=ROOT,
                      run_id=run_id, code_sha=code_sha, rules_sha=rules_sha,
                      manifest_path=manifest_path)
        if r.get("error"):
            any_error = True
        else:
            # P0-2: consume the prepared receipt (verifies published bytes match
            # the prepared SHA) rather than re-hashing whatever currently exists.
            dl.complete_prepared_receipt(manifest_path, k, BASE / k)
    # P0-1/P0-3: a fully successful run clears manifest + ledger; the identity
    # is archived into each book's provenance before the work-copy is removed.
    if not any_error:
        dl.clear_run_manifest(manifest_path, ledger_path)
    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
