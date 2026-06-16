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
import uuid

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
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    gender TEXT CHECK(gender IN ('male', 'female')),
                    birth_year INTEGER,
                    birth_month INTEGER,
                    birth_day INTEGER,
                    birth_hour INTEGER,
                    birth_minute INTEGER DEFAULT 0,
                    birth_location TEXT DEFAULT 'Beijing',
                    tags TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS client_charts (
                    client_id TEXT NOT NULL,
                    chart_id TEXT NOT NULL,
                    relation TEXT NOT NULL DEFAULT 'primary',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (client_id, chart_id),
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    client_id TEXT,
                    chart_id TEXT NOT NULL,
                    analysis_type TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT 'sihechu',
                    question TEXT NOT NULL DEFAULT '',
                    ai_text TEXT NOT NULL DEFAULT '',
                    structured_summary TEXT NOT NULL DEFAULT '{}',
                    report_tab TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    judgment_text TEXT NOT NULL,
                    is_accurate INTEGER NOT NULL CHECK(is_accurate IN (0, 1)),
                    user_comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_clients_updated ON clients(updated_at);
                CREATE INDEX IF NOT EXISTS idx_client_charts_client ON client_charts(client_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_client ON analyses(client_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_analyses_chart ON analyses(chart_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_feedback_analysis ON feedback(analysis_id);
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


# ============================================================
# Professional Workflow CRUD
# ============================================================

def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json_loads(value, default):
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def _client_from_row(row):
    if not row:
        return None
    d = dict(row)
    d['tags'] = _json_loads(d.get('tags'), [])
    return d


def _analysis_from_row(row):
    if not row:
        return None
    d = dict(row)
    d['structured_summary'] = _json_loads(d.get('structured_summary'), {})
    return d


def create_client(data):
    client_id = data.get('id') or _new_id('client')
    tags = data.get('tags') or []
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO clients (
                    id, name, gender, birth_year, birth_month, birth_day, birth_hour,
                    birth_minute, birth_location, tags, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    client_id,
                    data.get('name') or '',
                    data.get('gender'),
                    data.get('birth_year'),
                    data.get('birth_month'),
                    data.get('birth_day'),
                    data.get('birth_hour'),
                    data.get('birth_minute', 0),
                    data.get('birth_location', 'Beijing'),
                    json.dumps(tags, ensure_ascii=False),
                    data.get('notes', ''),
                )
            )
            conn.commit()
            row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
            return _client_from_row(row)
        finally:
            conn.close()


def list_clients(search='', tag=''):
    with _conn_lock:
        conn = _get_conn()
        try:
            if search:
                rows = conn.execute(
                    "SELECT * FROM clients WHERE name LIKE ? ORDER BY updated_at DESC",
                    (f"%{search}%",)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM clients ORDER BY updated_at DESC").fetchall()
            clients = [_client_from_row(r) for r in rows]
            if tag:
                clients = [c for c in clients if tag in c.get('tags', [])]
            return clients
        finally:
            conn.close()


def get_client(client_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
            return _client_from_row(row)
        finally:
            conn.close()


def update_client(client_id, data):
    allowed = {
        'name', 'gender', 'birth_year', 'birth_month', 'birth_day', 'birth_hour',
        'birth_minute', 'birth_location', 'tags', 'notes'
    }
    updates = []
    values = []
    for key in allowed:
        if key in data:
            updates.append(f"{key} = ?")
            value = json.dumps(data[key], ensure_ascii=False) if key == 'tags' else data[key]
            values.append(value)
    if not updates:
        return get_client(client_id)
    updates.append("updated_at = datetime('now','localtime')")
    values.append(client_id)
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(f"UPDATE clients SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
            return _client_from_row(row)
        finally:
            conn.close()


def delete_client(client_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            conn.commit()
        finally:
            conn.close()


def link_client_chart(client_id, chart_id, relation='primary'):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO client_charts (client_id, chart_id, relation)
                   VALUES (?, ?, ?)""",
                (client_id, chart_id, relation)
            )
            conn.commit()
        finally:
            conn.close()


def unlink_client_chart(client_id, chart_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM client_charts WHERE client_id = ? AND chart_id = ?", (client_id, chart_id))
            conn.commit()
        finally:
            conn.close()


def get_client_for_chart(chart_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT client_id FROM client_charts WHERE chart_id = ? LIMIT 1",
                (chart_id,),
            ).fetchone()
            return row["client_id"] if row else None
        finally:
            conn.close()


def list_client_charts(client_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT c.chart_id, c.name, c.birth_info, c.created_at, c.updated_at, cc.relation
                   FROM client_charts cc
                   JOIN charts c ON c.chart_id = cc.chart_id
                   WHERE cc.client_id = ?
                   ORDER BY cc.created_at DESC""",
                (client_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def save_analysis(client_id, chart_id, analysis_type, topic, question, ai_text, structured_summary=None, report_tab=None):
    analysis_id = _new_id('analysis')
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO analyses (
                    id, client_id, chart_id, analysis_type, topic, question,
                    ai_text, structured_summary, report_tab
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    client_id,
                    chart_id,
                    analysis_type,
                    topic,
                    question,
                    ai_text,
                    json.dumps(structured_summary or {}, ensure_ascii=False),
                    report_tab,
                )
            )
            conn.commit()
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            return _analysis_from_row(row)
        finally:
            conn.close()


def get_analysis(analysis_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            return _analysis_from_row(row)
        finally:
            conn.close()


def list_client_analyses(client_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM analyses WHERE client_id = ? ORDER BY created_at DESC",
                (client_id,)
            ).fetchall()
            return [_analysis_from_row(r) for r in rows]
        finally:
            conn.close()


def list_chart_analyses(chart_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM analyses WHERE chart_id = ? ORDER BY created_at DESC",
                (chart_id,)
            ).fetchall()
            return [_analysis_from_row(r) for r in rows]
        finally:
            conn.close()


def save_feedback(analysis_id, dimension, judgment_text, is_accurate, user_comment=''):
    feedback_id = _new_id('feedback')
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO feedback (
                    id, analysis_id, dimension, judgment_text, is_accurate, user_comment
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (feedback_id, analysis_id, dimension, judgment_text, 1 if is_accurate else 0, user_comment)
            )
            conn.commit()
            row = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
            return dict(row)
        finally:
            conn.close()


def get_feedback_stats():
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT dimension, COUNT(*) AS total, SUM(is_accurate) AS accurate
                   FROM feedback GROUP BY dimension"""
            ).fetchall()
            dimension_accuracy = {}
            for row in rows:
                total = row['total'] or 0
                accurate = row['accurate'] or 0
                dimension_accuracy[row['dimension']] = {
                    'total': total,
                    'accurate': accurate,
                    'accuracy': round(accurate / total, 3) if total else 0,
                }
            return {'dimension_accuracy': dimension_accuracy}
        finally:
            conn.close()


# Auto-initialize on import
init_db()
