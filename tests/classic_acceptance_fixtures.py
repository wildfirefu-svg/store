"""Shared fixtures for the classic-texts manual-acceptance tooling tests.

Everything runs offline: tiny synthetic datasets live under gitignored .tmp/
(NEVER pytest tmp dirs - sandbox permission issues); the big fake dataset
reproduces the EXACT real populations/strata/boundary/zero-chapter counts;
real-data tests read the frozen candidate commit via `git show` and run the
full production frozen-input lock. Not collected by pytest (no test_ prefix).
"""
import json
import os
import shutil
import subprocess
import sys
import time
import types
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT
SCRIPTS = ROOT / "scripts"
COMMIT = "80bc630396f31c6b6c122e49ef97f6d912e6f636"
CHAPTER_MANIFEST = ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json"
IDENTITY_MANIFEST = ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-candidate-identity-manifest.json"
ANCHOR_RECORD = ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-freeze-anchor-record.json"

sys.path.insert(0, str(SCRIPTS))
import classic_acceptance_common as c  # noqa: E402


def rmtree_force(path):
    def _chmod_retry(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_chmod_retry)


def tmp_dir(prefix):
    path = ROOT / ".tmp" / f"{prefix}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Bounded per-invocation wall time for test CLI subprocesses. This MUST stay
# BELOW the CI pytest per-test gate (--timeout=120) BY A COMFORTABLE MARGIN --
# and, crucially, that margin must also cover the cleanup work that runs after
# the bound fires. A wedged CLI is killed (and its whole process tree reaped)
# by THIS bound BEFORE pytest aborts the test; if pytest interrupted us first
# the cleanup would never run and the CLI + any frozen-chain checker it spawned
# would be orphaned. The post-timeout path is itself fully bounded and
# FAIL-CLOSED: every cleanup step (tree-kill, output drain) draws from ONE
# SHARED CLEANUP_TIMEOUT_SECONDS deadline instead of a fresh budget per step,
# so total worst-case wall time is timeout + CLEANUP_TIMEOUT_SECONDS =
# 100 + 5 = 105s, safely under 120s. The verdicts are also fail-closed: an
# uncertain tool result (timeout, nonzero exit) never counts as "process
# dead" or "tree reaped". Production invocations re-run the frozen lock (F18)
# once and measure ~70-75s.
CLI_TIMEOUT_SECONDS = 100
CLEANUP_TIMEOUT_SECONDS = 5


def _remaining(deadline):
    # Time left on a shared cleanup deadline; 0 once exhausted, so each
    # subsequent cleanup step gets at most the leftover -- never a fresh
    # CLEANUP_TIMEOUT_SECONDS budget that would stack serially.
    return max(0.0, deadline - time.monotonic())


def _script_path(script):
    # Accept either a bare script name (resolved under SCRIPTS) or an absolute
    # Path (e.g. a temp hang script created by a test).
    path = Path(script)
    return path if path.is_absolute() else SCRIPTS / path


def _bounded_subprocess(argv, timeout):
    # subprocess.run with an explicit, SHORT timeout: never let an external
    # housekeeping command (taskkill / tasklist) block the cleanup path for
    # longer than the cleanup budget. Returns the result, or None on timeout.
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def _kill_process_tree(proc, deadline):
    # Terminate the spawned CLI AND every descendant (a CLI may itself spawn
    # the frozen-chain checker). taskkill /T walks the tree on Windows; on
    # POSIX we send SIGKILL to the process group we put the child in. Every
    # external call draws from the SHARED deadline, and the verdict is
    # fail-closed: True only when the whole tree is PROVABLY dead (taskkill
    # exits 0 / SIGKILL delivered); a tool timeout (None), a nonzero exit, or
    # a spawn failure is UNCERTAIN and returns False -- the caller must not
    # report a reaped tree. proc.kill() on the direct child is always
    # attempted as a last resort but never upgrades the verdict by itself.
    try:
        if os.name == "nt":
            r = _bounded_subprocess(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                    _remaining(deadline))
            tree_ok = bool(r) and r.returncode == 0
        else:
            import signal
            # The child was started with start_new_session=True, so its PGID
            # IS proc.pid. Kill by that KNOWN pgid directly -- NOT getpgid:
            # once the group leader (the direct child) has exited but a
            # descendant still sits in the group, getpgid(proc.pid) raises
            # ProcessLookupError and the code below would wrongly report the
            # tree as reaped (a false-green). killpg(proc.pid) reaches the
            # whole group even without the leader, and only raises ESRCH when
            # the group has no member left -- which genuinely proves death.
            os.killpg(proc.pid, signal.SIGKILL)
            tree_ok = True
    except ProcessLookupError:
        tree_ok = True  # the pid/group is already gone: provably dead
    except (PermissionError, OSError):
        tree_ok = False  # could not deliver the kill: uncertain
    try:
        proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return tree_ok


def _drain_output(proc, deadline):
    # Drain the killed child's pipes within the SAME shared deadline so a
    # grandchild that holds the pipe open cannot block us indefinitely, and
    # so the drain never spends a second full cleanup budget; fall back to
    # whatever was captured so far. proc is already being torn down.
    try:
        return proc.communicate(timeout=_remaining(deadline))
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            return proc.communicate(timeout=_remaining(deadline))
        except subprocess.TimeoutExpired:
            return "", ""


def _pid_alive(pid):
    # Fail-closed liveness probe: only a SUCCESSFUL tasklist (exit 0 --
    # verified: "no tasks running" is also exit 0) whose output lacks the pid
    # proves death. A tool timeout (None), a nonzero exit, or a spawn failure
    # is UNCERTAIN and must be reported ALIVE, so a caller can never mistake
    # "unknown" for "dead" (no false-green cleanup checks).
    if not pid:
        return False
    if os.name == "nt":
        r = _bounded_subprocess(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                                CLEANUP_TIMEOUT_SECONDS)
        if r is None or r.returncode != 0:
            return True
        return str(int(pid)) in r.stdout
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def run_argv_result(argv, timeout=CLI_TIMEOUT_SECONDS):
    """Bounded runner for a FULLY-ASSEMBLED argv (must already include the
    python interpreter as argv[0]). Same timeout/process-tree contract as
    run_cli_result; use this when a test builds the argv list itself. The
    timeout AND the post-timeout cleanup are both bounded (one shared
    CLEANUP_TIMEOUT_SECONDS budget), so this returns in at most timeout +
    CLEANUP_TIMEOUT_SECONDS wall time and never hands an unbounded wait back
    to the pytest 120s gate. .cleanup_ok is fail-closed: True only when the
    tree-kill provably succeeded; a timeout/nonzero tool result reports
    False instead of claiming a reaped tree."""
    popen_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", errors="replace")
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen([str(x) for x in argv], **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return types.SimpleNamespace(returncode=proc.returncode, stdout=stdout,
                                     stderr=stderr, pid=proc.pid, timed_out=False,
                                     cleanup_ok=True)
    except subprocess.TimeoutExpired:
        # ONE shared cleanup budget: the tree-kill and the output drain both
        # draw from the same deadline, so the post-timeout path costs at most
        # CLEANUP_TIMEOUT_SECONDS once (not once per step).
        deadline = time.monotonic() + CLEANUP_TIMEOUT_SECONDS
        cleanup_ok = _kill_process_tree(proc, deadline)
        stdout, stderr = _drain_output(proc, deadline)
        return types.SimpleNamespace(returncode=proc.returncode, stdout=stdout,
                                     stderr=stderr, pid=proc.pid, timed_out=True,
                                     cleanup_ok=cleanup_ok)


def run_cli_result(script, *args, timeout=CLI_TIMEOUT_SECONDS):
    """Run a CLI subprocess with a BOUNDED timeout and full process-tree
    cleanup. Returns a result namespace with .returncode / .stdout / .stderr /
    .pid / .timed_out / .cleanup_ok -- usable by BOTH success callers and
    expected-failure callers (which assert .returncode != 0). On timeout the
    CLI and every descendant are killed and reaped, then .timed_out is True
    (no exception): the timeout/process-tree test asserts the child+
    grandchild PIDs are gone; .cleanup_ok is fail-closed -- False when the
    tree-kill itself timed out or failed, never a silent false-green."""
    argv = [sys.executable, str(_script_path(script)), *(str(x) for x in args)]
    return run_argv_result(argv, timeout=timeout)


def run_cli(script, *args, timeout=CLI_TIMEOUT_SECONDS):
    res = run_cli_result(script, *args, timeout=timeout)
    cmd = f"{script} {' '.join(map(str, args))}"
    assert not res.timed_out, f"{cmd} timed out after {timeout}s (process tree killed):\n{res.stdout}\n{res.stderr}"
    assert res.returncode == 0, f"{cmd} failed:\n{res.stdout}\n{res.stderr}"
    return res.stdout


def sha256_file(path):
    """F20: raw on-disk byte SHA for review-chain artifacts. No LF
    normalization (CRLF tampering must change the binding SHA)."""
    return c.sha256_bytes(Path(path).read_bytes())


def write_json(path, obj):
    Path(path).write_bytes(c.serialize_json(obj))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finding(severity, category):
    return {"severity": severity, "category": category, "evidence_text": "evidence",
            "note": "", "reviewer": "reviewer-1", "reviewed_at": "2026-08-23T00:00:00+08:00"}


def critical():
    return finding("critical", "distortion")


def minor():
    return finding("minor", "wording")


# tiny dataset: 4 sanmingtonghui chapters (1,2,3 in stratum 1; 85 in stratum 2;
# ch1 is a boundary chapter) + 8 rules/8 mcqs per other book.
TINY_CHAPTERS = {1: (2, 2), 2: (6, 6), 3: (6, 6), 85: (6, 6)}
TINY_SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/" + "e" * 64


def build_tiny_dataset(base):
    base = Path(base)
    rules, mcqs, chapters = [], [], []
    for ci, (nr, nm) in sorted(TINY_CHAPTERS.items()):
        raw_rel = f"{TINY_SNAP}/extracted/raw_{ci:03d}.txt"
        p = base / raw_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"第{ci}章 原文 甲乙丙丁。\n", encoding="utf-8", newline="\n")
        rule_ids = [f"tiny_{ci:03d}_r{i:03d}" for i in range(nr)]
        mcq_ids = [f"tiny_{ci:03d}_m{i:03d}" for i in range(nm)]
        chapters.append({"chapter_index": ci, "title": f"第{ci}章", "is_legacy": ci <= 80,
                         "raw_source_path": raw_rel, "rule_ids": rule_ids, "mcq_ids": mcq_ids,
                         "rule_count": nr, "mcq_count": nm,
                         "zero_rule": nr == 0, "zero_mcq": nm == 0})
        for i in range(nr):
            rules.append({"id": f"tiny_{ci:03d}_r{i:03d}", "category": "测试", "subject": "测试",
                          "condition": "测试条件", "rule": f"第{ci}章规则{i}。",
                          "original_text": "原文 甲乙丙丁", "source_book": "三命通会",
                          "source_chapter": str(ci)})
        for i in range(nm):
            mcqs.append({"question": f"第{ci}章问题{i}？",
                         "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                         "answer": "A", "explanation": "解释。", "difficulty": "初级",
                         "category": "测试", "source_rule_id": f"tiny_{ci:03d}_r000",
                         "id": f"tiny_{ci:03d}_m{i:03d}"})
    sm_dir = base / "knowledge_base" / "classic_texts" / "sanmingtonghui"
    write_json(sm_dir / "all_rules.json", rules)
    (sm_dir / "all_mcq.jsonl").write_bytes(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs).encode("utf-8"))
    for book in ("qiongtongbaojian", "ditiansui", "zipingzhenquan"):
        bdir = base / "knowledge_base" / "classic_texts" / book
        bdir.mkdir(parents=True, exist_ok=True)
        brules = [{"id": f"{book}_r{i:03d}", "category": "测试", "subject": "测试",
                   "condition": "测试", "rule": f"{book}规则{i}。",
                   "original_text": f"{book}原文{i}", "source_book": book,
                   "source_chapter": f"一、{book}节{i}"} for i in range(8)]
        bmcqs = [{"question": f"{book}问题{i}？",
                  "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                  "answer": "A", "explanation": "解释。", "difficulty": "初级",
                  "category": "测试", "source_rule_id": f"{book}_r{i:03d}",
                  "id": f"{book}_m{i:03d}"} for i in range(8)]
        write_json(bdir / "all_rules.json", brules)
        (bdir / "all_mcq.jsonl").write_bytes(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in bmcqs).encode("utf-8"))
    (base / "knowledge_base" / "classic_texts" / "qiongtongbaojian"
     / "quarantine_rules.jsonl").write_bytes(b'{"id": "tiny_q_1"}\n')
    chman = {"schema_version": "1.0", "chapter_count": len(chapters),
             "zero_rule_chapters": [], "zero_mcq_chapters": [], "chapters": chapters}
    chman_path = base / "chapter_manifest.json"
    write_json(chman_path, chman)
    return base, chman_path


# ---- big fake dataset: EXACT real populations / strata / boundary counts /
# zero-output chapters (design section 3.3/4.2/4.3 with the v4.6.1 errata).
STRATA = [(1, 1, 80), (2, 81, 89), (3, 90, 162), (4, 163, 184), (5, 185, 244),
          (6, 245, 304), (7, 305, 346), (8, 347, 367), (9, 368, 383)]
POP = {1: (1542, 777), 2: (74, 59), 3: (708, 593), 4: (291, 211), 5: (1320, 1226),
       6: (1274, 1187), 7: (1108, 843), 8: (505, 367), 9: (1221, 840)}
BOUNDARY_COUNTS = {1: (14, 14), 80: (1, 1), 81: (2, 2), 90: (15, 14), 163: (28, 4),
                   185: (40, 38), 245: (35, 32), 305: (15, 14), 347: (12, 9),
                   368: (81, 49), 383: (24, 17)}
ZERO_RULE = {25, 56, 72}
ZERO_MCQ = {25, 26, 56, 72, 112}
OTHER_POP = {"qiongtongbaojian": (2312, 2120), "ditiansui": (799, 646),
             "zipingzhenquan": (156, 155)}
FAKE_SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/" + "f" * 64


def _distribute(total, chapters):
    assert total >= len(chapters) >= 1
    base, extra = divmod(total - len(chapters), len(chapters))
    return {ci: 1 + base + (1 if i < extra else 0) for i, ci in enumerate(chapters)}


def build_fake_dataset(base):
    base = Path(base)
    rule_counts, mcq_counts = {}, {}
    for _idx, lo, hi in STRATA:
        pop_r, pop_m = POP[_idx]
        chs = list(range(lo, hi + 1))
        dist_r = [ci for ci in chs if ci not in ZERO_RULE and ci not in BOUNDARY_COUNTS]
        dist_m = [ci for ci in chs if ci not in ZERO_MCQ and ci not in BOUNDARY_COUNTS]
        b_r = sum(BOUNDARY_COUNTS[ci][0] for ci in chs if ci in BOUNDARY_COUNTS)
        b_m = sum(BOUNDARY_COUNTS[ci][1] for ci in chs if ci in BOUNDARY_COUNTS)
        counts_r = _distribute(pop_r - b_r, dist_r)
        counts_m = _distribute(pop_m - b_m, dist_m)
        for ci in chs:
            rule_counts[ci] = (BOUNDARY_COUNTS[ci][0] if ci in BOUNDARY_COUNTS
                               else counts_r.get(ci, 0))
            mcq_counts[ci] = (BOUNDARY_COUNTS[ci][1] if ci in BOUNDARY_COUNTS
                              else counts_m.get(ci, 0))
    assert sum(rule_counts.values()) == 8043
    assert sum(mcq_counts.values()) == 6103
    assert {ci for ci, n in rule_counts.items() if n == 0} == ZERO_RULE
    assert {ci for ci, n in mcq_counts.items() if n == 0} == ZERO_MCQ
    chapters, rules, mcqs = [], [], []
    for ci in range(1, 384):
        raw_rel = f"{FAKE_SNAP}/extracted/raw_{ci:03d}.txt"
        p = base / raw_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(
            (f"第{ci}章 原文内容 其一。\n第{ci}章 原文内容 其二。\n").encode("utf-8"))
        rule_ids = [f"smth_{ci:03d}_r{i:04d}" for i in range(rule_counts[ci])]
        mcq_ids = [f"smth_{ci:03d}_m{i:04d}" for i in range(mcq_counts[ci])]
        chapters.append({"chapter_index": ci, "title": f"第{ci}章·测试",
                         "is_legacy": ci <= 80, "raw_source_path": raw_rel,
                         "rule_ids": rule_ids, "mcq_ids": mcq_ids,
                         "rule_count": len(rule_ids), "mcq_count": len(mcq_ids),
                         "zero_rule": ci in ZERO_RULE, "zero_mcq": ci in ZERO_MCQ})
        for i in range(rule_counts[ci]):
            rules.append({"id": f"smth_{ci:03d}_r{i:04d}", "category": "测试",
                          "subject": "测试", "condition": "测试条件",
                          "rule": f"第{ci}章测试规则{i}。",
                          "original_text": f"第{ci}章 原文内容其一",
                          "source_book": "三命通会", "source_chapter": str(ci)})
        for i in range(mcq_counts[ci]):
            mcqs.append({"question": f"第{ci}章测试问题{i}？",
                         "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                         "answer": "A", "explanation": "测试解释。",
                         "difficulty": "初级", "category": "测试",
                         "source_rule_id": f"smth_{ci:03d}_r0000",
                         "id": f"smth_{ci:03d}_m{i:04d}"})
    sm_dir = base / "knowledge_base" / "classic_texts" / "sanmingtonghui"
    write_json(sm_dir / "all_rules.json", rules)
    (sm_dir / "all_mcq.jsonl").write_bytes(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs).encode("utf-8"))
    for book, (nr, nm) in OTHER_POP.items():
        bdir = base / "knowledge_base" / "classic_texts" / book
        bdir.mkdir(parents=True, exist_ok=True)
        brules = [{"id": f"{book}_r{i:05d}", "category": "测试", "subject": "测试",
                   "condition": "测试", "rule": f"{book}测试规则{i}。",
                   "original_text": f"{book}原文{i}", "source_book": book,
                   "source_chapter": f"一、测试节{i}"} for i in range(nr)]
        bmcqs = [{"question": f"{book}测试问题{i}？",
                  "options": {"A": "对", "B": "错", "C": "否", "D": "疑"},
                  "answer": "A", "explanation": "测试解释。", "difficulty": "初级",
                  "category": "测试", "source_rule_id": f"{book}_r{i:05d}",
                  "id": f"{book}_m{i:05d}"} for i in range(nm)]
        write_json(bdir / "all_rules.json", brules)
        (bdir / "all_mcq.jsonl").write_bytes(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in bmcqs).encode("utf-8"))
    (base / "knowledge_base" / "classic_texts" / "qiongtongbaojian"
     / "quarantine_rules.jsonl").write_bytes(b'{"id": "fake_q_1"}\n')
    chman = {"schema_version": "1.0", "chapter_count": 383,
             "zero_rule_chapters": sorted(ZERO_RULE),
             "zero_mcq_chapters": sorted(ZERO_MCQ), "chapters": chapters}
    chman_path = base / "chapter_manifest.json"
    write_json(chman_path, chman)
    return base, chman_path


# review-fill helpers: first reviewer defaults to "e2e-r1", second to
# "e2e-r2", arbitrator to "e2e-arb" (all pairwise distinct, F15).

def make_primary(packet_path, out_path, verdicts=None, default="PASS",
                 first_reviewer="e2e-r1"):
    packet = read_json(packet_path)
    items = []
    for e in packet["items"]:
        key = (e["book"], e["type"], e["id"])
        verdict, findings = (verdicts or {}).get(key, (default, []))
        fs = []
        for f in findings:
            f = dict(f)
            f["reviewer"] = first_reviewer
            f.setdefault("reviewed_at", "2026-08-23T00:00:00+08:00")
            fs.append(f)
        items.append({"item": {"book": e["book"], "type": e["type"], "id": e["id"],
                               "source_chapter": e.get("source_chapter")},
                      "verdict": verdict, "findings": fs})
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": packet["sample_manifest_sha256"],
               "expansion_manifests_sha256": packet.get("expansion_manifests_sha256") or [],
               "items": items, "overall_stats": {"note": "recomputed by decide"},
               "zero_output_report": packet["integrity"]["zero_output_chapters"],
               "reviewer_list": [first_reviewer]}
    write_json(out_path, primary)
    return str(out_path)


def make_second(primary_path, out_path, agree=None, default_agree=True,
                second_reviewer="e2e-r2"):
    primary = read_json(primary_path)
    entries = []
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry["findings"]):
            if f["severity"] != "critical":
                continue
            ref = (item["book"], item["type"], item["id"], idx)
            a = agree.get(ref, default_agree) if agree else default_agree
            entries.append({"book": item["book"], "type": item["type"], "id": item["id"],
                            "finding_index": idx, "first_severity": "critical",
                            "first_category": f["category"], "agree": a,
                            "evidence_text": "e2e second review evidence",
                            "reviewer": second_reviewer,
                            "reviewed_at": "2026-08-23T00:00:00+08:00"})
    receipt = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
               "primary_sha256": sha256_file(primary_path), "reviewer": second_reviewer,
               "reviewed_at": "2026-08-23T00:00:00+08:00", "entries": entries}
    write_json(out_path, receipt)
    return str(out_path)


def make_arbitration(primary_path, second_path, out_path, decisions=None,
                     default_decision="critical", arbitrator="e2e-arb"):
    primary = read_json(primary_path)
    second = read_json(second_path)
    first_by_ref = {}
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry["findings"]):
            if f["severity"] == "critical":
                first_by_ref[(item["book"], item["type"], item["id"], idx)] = f["reviewer"]
    entries = []
    for e in second["entries"]:
        if e["agree"]:
            continue
        ref = (e["book"], e["type"], e["id"], e["finding_index"])
        d = decisions.get(ref, default_decision) if decisions else default_decision
        entries.append({"book": e["book"], "type": e["type"], "id": e["id"],
                        "finding_index": e["finding_index"], "reviewer_first": first_by_ref[ref],
                        "decision": d, "reasoning": "e2e arbitration reasoning",
                        "arbitrator": arbitrator,
                        "reviewed_at": "2026-08-23T00:00:00+08:00"})
    receipt = {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
               "primary_sha256": sha256_file(primary_path),
               "second_review_sha256": sha256_file(second_path),
               "reviewer_first": None, "reviewer_second": second["reviewer"],
               "arbitrator": arbitrator, "reviewed_at": "2026-08-23T00:00:00+08:00",
               "entries": entries}
    write_json(out_path, receipt)
    return str(out_path)
