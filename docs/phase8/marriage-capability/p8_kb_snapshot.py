"""P8-2B 前置：KB 最小 SQLite 快照 + 查询集 + classic_texts 冻结 + 等价性校验。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md v1.3.1（§3/§P8-2B）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md v3.2（Task 3）
零 API、只读原库（URI mode=ro）；审计只允许打快照。

入口 SQL 为 knowledge-base/bazi_kb.py（:253-306）冻结实现的只读镜像，
逐条注释引用源行号；FTS5 直接 MATCH 与入口结果比对以证明未走 LIKE fallback。
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"
SOURCE_DB = REPO / "knowledge-base" / "bazi_kb.db"
SNAP_DB = P8_DIR / "kb_snapshot.db"

# 快照覆盖映射全部表（计划 v3.2 冻结）；ziwei_patterns 无公开入口不进快照。
SNAPSHOT_TABLES = [
    "gejue", "gejue_fts", "gejue_fts_data", "gejue_fts_idx",
    "gejue_fts_docsize", "gejue_fts_config",
    "shishen_combos", "shensha", "nayin", "bingyao", "xiangyi",
]
EXCLUDED_TABLES = ["ziwei_patterns", "yangzhai", "wuyun_liuqi"]

CLASSIC_TEXT_BOOKS = ["ditiansui", "qiongtongbaojian", "sanmingtonghui", "zipingzhenquan"]

PROBE_QUERIES = [
    {"entrypoint": "search_gejue", "args": {"query": "婚姻", "category": None}, "top_n": 5},
    {"entrypoint": "search_shishen_combo", "args": {"combo_name": "官星"}, "top_n": 5},
    {"entrypoint": "search_shensha", "args": {"name": "红鸾"}, "top_n": None},
    {"entrypoint": "search_nayin", "args": {"gan": "甲", "zhi": "子"}, "top_n": None},
    {"entrypoint": "search_bingyao", "args": {"query": "火"}, "top_n": 5},
    {"entrypoint": "search_xiangyi", "args": {"gan_or_zhi": "甲"}, "top_n": 10},
]


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot_db(src: Path, dst: Path, tables: list[str], excluded: list[str]) -> dict:
    """backup API 全量复制后删除非审计表，保留 FTS5 结构。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    with _connect_ro(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)
        for table in excluded:
            d.execute(f"DROP TABLE IF EXISTS {table}")
        d.commit()
    with sqlite3.connect(dst) as d:
        present = sorted(
            r[0]
            for r in d.execute("SELECT name FROM sqlite_master WHERE type IN ('table','virtual')")
        )
    return {"tables": present, "source": str(src), "snapshot": str(dst)}


# ---- 入口 SQL 镜像（只读；源：knowledge-base/bazi_kb.py:253-306） ----

def _run_entrypoint(conn: sqlite3.Connection, entrypoint: str, args: dict, top_n):
    """返回 (rows, fallback_used)。fallback_used 仅 search_gejue 无 category 的 FTS 路径可能为 True。"""
    fallback = False
    if entrypoint == "search_gejue":
        query = args["query"]
        category = args.get("category")
        if category:
            rows = conn.execute(
                "SELECT g.*, g.rowid AS _rowid FROM gejue g WHERE g.category=? "
                "AND (g.text LIKE ? OR g.keywords LIKE ?) LIMIT ?",
                (category, f"%{query}%", f"%{query}%", top_n),
            ).fetchall()
        else:
            try:
                rows = conn.execute(
                    "SELECT g.*, g.rowid AS _rowid FROM gejue g INNER JOIN "
                    "(SELECT rowid, rank FROM gejue_fts WHERE gejue_fts MATCH ? "
                    "ORDER BY rank LIMIT ?) f ON g.rowid = f.rowid",
                    (query, top_n),
                ).fetchall()
            except sqlite3.OperationalError:
                fallback = True
                rows = conn.execute(
                    "SELECT g.*, g.rowid AS _rowid FROM gejue g "
                    "WHERE g.text LIKE ? OR g.keywords LIKE ? LIMIT ?",
                    (f"%{query}%", f"%{query}%", top_n),
                ).fetchall()
    elif entrypoint == "search_shishen_combo":
        rows = conn.execute(
            "SELECT * FROM shishen_combos WHERE combo LIKE ? LIMIT ?",
            (f"%{args['combo_name']}%", top_n),
        ).fetchall()
    elif entrypoint == "search_shensha":
        rows = conn.execute(
            "SELECT * FROM shensha WHERE name LIKE ? LIMIT 1", (f"%{args['name']}%",)
        ).fetchall()
    elif entrypoint == "search_nayin":
        rows = conn.execute(
            "SELECT * FROM nayin WHERE gan_zhi=? LIMIT 1", (args["gan"] + args["zhi"],)
        ).fetchall()
    elif entrypoint == "search_bingyao":
        q = f"%{args['query']}%"
        rows = conn.execute(
            "SELECT * FROM bingyao WHERE disease LIKE ? OR symptom LIKE ? LIMIT ?",
            (q, q, top_n),
        ).fetchall()
    elif entrypoint == "search_xiangyi":
        rows = conn.execute(
            "SELECT * FROM xiangyi WHERE gan_or_zhi LIKE ? LIMIT ?",
            (f"%{args['gan_or_zhi']}%", top_n),
        ).fetchall()
    else:  # pragma: no cover - 白名单外入口 fail-closed
        raise ValueError(f"unknown entrypoint: {entrypoint}")
    return rows, fallback


def _fts_direct_rowids(conn: sqlite3.Connection, query: str, top_n):
    try:
        rows = conn.execute(
            "SELECT rowid FROM gejue_fts WHERE gejue_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, top_n),
        ).fetchall()
        return [r["rowid"] for r in rows], True
    except sqlite3.OperationalError:
        return [], False


def _canonical(rows) -> list[str]:
    return [json.dumps(dict(r), sort_keys=True, ensure_ascii=False) for r in rows]


def run_equivalence(qset_path: Path, probe_queries: list[dict], src_db: Path,
                    snap_db: Path, out_path: Path) -> dict:
    qset = json.loads(qset_path.read_text(encoding="utf-8"))
    entries = [dict(q) | {"source": "kb_query_set"} for q in qset["queries"]]
    for i, p in enumerate(probe_queries, start=1):
        entries.append(dict(p) | {"query_id": f"probe-{i}", "source": "probe"})
    results = []
    with _connect_ro(src_db) as src, _connect_ro(snap_db) as snap:
        for q in entries:
            args, top_n, ep = q["args"], q["top_n"], q["entrypoint"]
            rows_src, fallback = _run_entrypoint(src, ep, args, top_n)
            rows_snap, _ = _run_entrypoint(snap, ep, args, top_n)
            ids_src = [r["id"] for r in rows_src]
            ids_snap = [r["id"] for r in rows_snap]
            record = {
                "query_id": q["query_id"],
                "entrypoint": ep,
                "args": args,
                "top_n": top_n,
                "source": q["source"],
                "source_hits": len(ids_src),
                "snapshot_hits": len(ids_snap),
                "ids_equal": ids_src == ids_snap,
                "order_equal": ids_src == ids_snap,
                "content_equal": _canonical(rows_src) == _canonical(rows_snap),
                "fallback_used": fallback,
                "fts_direct_match": None,
            }
            if ep == "search_gejue" and not args.get("category"):
                direct, direct_ok = _fts_direct_rowids(src, args["query"], top_n)
                entry_rowids = [r["_rowid"] for r in rows_src]
                record["fts_direct_match"] = direct_ok and entry_rowids == direct
                record["order_equal"] = record["order_equal"] and (
                    record["ids_equal"] and not direct_ok or entry_rowids == direct
                )
            record["ok"] = (
                record["source_hits"] == record["snapshot_hits"]
                and record["ids_equal"]
                and record["order_equal"]
                and record["content_equal"]
                and (record["fts_direct_match"] is not False)
            )
            results.append(record)
    payload = {
        "schema_version": "1.0",
        "source_db": str(src_db.relative_to(REPO)),
        "snapshot_db": str(snap_db.relative_to(REPO)),
        "queries": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r["ok"]),
            "fallback_used": sum(1 for r in results if r["fallback_used"]),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def build_query_set(rk_path: Path, out_path: Path) -> dict:
    rows = [json.loads(l) for l in rk_path.open(encoding="utf-8") if l.strip()]
    grouped: dict[tuple, dict] = {}
    for row in rows:
        for item in row["items"]:
            for qs in item["query_specs"]:
                key = (qs["entrypoint"], json.dumps(qs["args"], sort_keys=True))
                entry = grouped.get(key)
                if entry is None:
                    entry = {
                        "query_id": qs["query_id"],
                        "entrypoint": qs["entrypoint"],
                        "args": qs["args"],
                        "top_n": qs["top_n"],
                        "sources": [],
                    }
                    grouped[key] = entry
                entry["sources"].append(
                    {"item_id": item["item_id"], "query_id": qs["query_id"]}
                )
                if qs["top_n"] is not None:
                    entry["top_n"] = max(entry["top_n"] or 0, qs["top_n"])
    queries = [grouped[k] for k in sorted(grouped)]
    payload = {
        "schema_version": "1.0",
        "source": "docs/phase8/marriage-capability/required_knowledge.jsonl",
        "queries": queries,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def _git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def build_classic_texts_freeze(out_path: Path, head: str | None = None) -> dict:
    head = head or _git(["rev-parse", "HEAD"])
    files = []
    for book in CLASSIC_TEXT_BOOKS:
        for name in ("all_rules.json", "quarantine_rules.jsonl"):
            path = f"knowledge_base/classic_texts/{book}/{name}"
            blob = _git(["rev-parse", f"{head}:{path}"])
            files.append({"path": path, "blob_sha": blob, "commit": head})
    payload = {"schema_version": "1.0", "frozen_commit": head, "files": files}
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> None:
    snapshot_db(SOURCE_DB, SNAP_DB, SNAPSHOT_TABLES, EXCLUDED_TABLES)
    build_query_set(P8_DIR / "required_knowledge.jsonl", P8_DIR / "kb_query_set.json")
    build_classic_texts_freeze(P8_DIR / "classic_texts_freeze.json")
    run_equivalence(
        P8_DIR / "kb_query_set.json",
        PROBE_QUERIES,
        SOURCE_DB,
        SNAP_DB,
        P8_DIR / "kb_equivalence.json",
    )
    print(f"snapshot+query_set+freeze+equivalence written to {P8_DIR}")


if __name__ == "__main__":
    main()
