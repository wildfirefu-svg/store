#!/usr/bin/env python3
"""
SQLite persistence layer for BaZi analysis data.
Stores charts, chat history, and reports — survives app restarts.

Tables:
  - charts: mingzhu list with birth info + chart data
  - chat_history: per-chart chat messages
  - reports: per-chart report cache (tab → content)
"""
import json
import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bazi_data.db")

_conn_lock = threading.Lock()


def _get_conn():
    """Get a thread-safe connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS charts (
                    chart_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    birth_info TEXT NOT NULL DEFAULT '{}',
                    chart_data TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chart_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    tool TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chat_chart ON chat_history(chart_id, id);
                CREATE TABLE IF NOT EXISTS reports (
                    chart_id TEXT NOT NULL,
                    tab_id TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (chart_id, tab_id),
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
                );
            """)
            conn.commit()
        finally:
            conn.close()


# ============================================================
# Charts CRUD
# ============================================================

def list_charts():
    """Return all saved charts (summary only, no raw chart_data)."""
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT chart_id, name, birth_info, created_at, updated_at FROM charts ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_chart(chart_id):
    """Get full chart data by ID."""
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM charts WHERE chart_id = ?", (chart_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d['chart_data'] = json.loads(d['chart_data'])
            d['birth_info'] = json.loads(d['birth_info'])
            return d
        finally:
            conn.close()


def save_chart(chart_id, name, birth_info, chart_data):
    """Insert or update a chart."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO charts (chart_id, name, birth_info, chart_data, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now','localtime'))""",
                (chart_id, name, json.dumps(birth_info, ensure_ascii=False),
                 json.dumps(chart_data, ensure_ascii=False))
            )
            conn.commit()
        finally:
            conn.close()


def delete_chart(chart_id):
    """Delete a chart and its associated chat history + reports (CASCADE)."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM charts WHERE chart_id = ?", (chart_id,))
            conn.commit()
        finally:
            conn.close()


# ============================================================
# Chat History CRUD
# ============================================================

def get_chat_history(chart_id, limit=500):
    """Get chat messages for a chart, oldest first."""
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT id, role, text, tool, created_at FROM chat_history "
                "WHERE chart_id = ? ORDER BY id ASC LIMIT ?",
                (chart_id, limit)
            ).fetchall()
            # Convert to frontend-compatible format
            return [{'role': r['role'], 'text': r['text'], 'tool': r['tool']} for r in rows]
        finally:
            conn.close()


def append_chat_message(chart_id, role, text, tool=None):
    """Append a single chat message."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO chat_history (chart_id, role, text, tool) VALUES (?, ?, ?, ?)",
                (chart_id, role, text, tool)
            )
            conn.commit()
            # Keep only last 500 messages per chart
            conn.execute(
                """DELETE FROM chat_history WHERE chart_id = ? AND id NOT IN (
                    SELECT id FROM chat_history WHERE chart_id = ? ORDER BY id DESC LIMIT 500
                )""",
                (chart_id, chart_id)
            )
            conn.commit()
        finally:
            conn.close()


def clear_chat_history(chart_id):
    """Delete all chat messages for a chart."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM chat_history WHERE chart_id = ?", (chart_id,))
            conn.commit()
        finally:
            conn.close()


# ============================================================
# Reports CRUD
# ============================================================

def get_reports(chart_id):
    """Get all report tabs for a chart."""
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT tab_id, content FROM reports WHERE chart_id = ?",
                (chart_id,)
            ).fetchall()
            return {r['tab_id']: r['content'] for r in rows}
        finally:
            conn.close()


def save_report(chart_id, tab_id, content):
    """Save/update a report tab."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO reports (chart_id, tab_id, content, updated_at)
                   VALUES (?, ?, ?, datetime('now','localtime'))""",
                (chart_id, tab_id, content)
            )
            conn.commit()
        finally:
            conn.close()


def delete_report(chart_id, tab_id):
    """Delete a specific report tab."""
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "DELETE FROM reports WHERE chart_id = ? AND tab_id = ?",
                (chart_id, tab_id)
            )
            conn.commit()
        finally:
            conn.close()


# Auto-initialize on import
init_db()
