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


def _ensure_columns(conn, table, columns):
    existing = {row['name'] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


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
                CREATE TABLE IF NOT EXISTS model_outputs (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT,
                    chart_id TEXT,
                    client_id TEXT,
                    provider TEXT,
                    model TEXT,
                    method TEXT,
                    prompt_version TEXT,
                    reasoning_protocol TEXT,
                    domain TEXT,
                    question TEXT,
                    input_hash TEXT,
                    raw_prompt TEXT,
                    raw_output TEXT,
                    parsed_answer TEXT,
                    structured_reasoning_json TEXT,
                    latency_ms INTEGER,
                    token_estimate INTEGER,
                    cost_estimate REAL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE SET NULL,
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE,
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_clients_updated ON clients(updated_at);
                CREATE INDEX IF NOT EXISTS idx_client_charts_client ON client_charts(client_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_client ON analyses(client_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_analyses_chart ON analyses(chart_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_feedback_analysis ON feedback(analysis_id);
                CREATE INDEX IF NOT EXISTS idx_model_outputs_chart_id ON model_outputs(chart_id);
                CREATE INDEX IF NOT EXISTS idx_model_outputs_analysis_id ON model_outputs(analysis_id);
                CREATE INDEX IF NOT EXISTS idx_model_outputs_prompt_version ON model_outputs(prompt_version);
                CREATE TABLE IF NOT EXISTS benchmark_cases (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'internal',
                    person_id TEXT,
                    name TEXT NOT NULL DEFAULT '',
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    chart_input_json TEXT NOT NULL DEFAULT '{}',
                    chart_result_json TEXT NOT NULL DEFAULT '{}',
                    verified_events_json TEXT NOT NULL DEFAULT '[]',
                    anonymized INTEGER NOT NULL DEFAULT 1,
                    license_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_cases_source ON benchmark_cases(source);
                CREATE TABLE IF NOT EXISTS benchmark_questions (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    domain TEXT NOT NULL DEFAULT 'unknown',
                    question TEXT NOT NULL DEFAULT '',
                    options_json TEXT NOT NULL DEFAULT '[]',
                    answer TEXT NOT NULL DEFAULT '',
                    expected_evidence_json TEXT NOT NULL DEFAULT '[]',
                    difficulty TEXT NOT NULL DEFAULT 'medium',
                    evaluator_notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (case_id) REFERENCES benchmark_cases(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_questions_case ON benchmark_questions(case_id);
                CREATE INDEX IF NOT EXISTS idx_benchmark_questions_domain ON benchmark_questions(domain);
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    method TEXT NOT NULL DEFAULT 'structured',
                    prompt_version TEXT NOT NULL DEFAULT '',
                    reasoning_protocol TEXT NOT NULL DEFAULT '',
                    n_cases INTEGER NOT NULL DEFAULT 0,
                    n_questions INTEGER NOT NULL DEFAULT 0,
                    accuracy REAL,
                    evidence_score REAL,
                    stability_score REAL,
                    safety_score REAL,
                    report_path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_runs_dataset ON benchmark_runs(dataset);
                CREATE INDEX IF NOT EXISTS idx_benchmark_runs_model ON benchmark_runs(model);
                CREATE TABLE IF NOT EXISTS life_events (
                    id TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL,
                    client_id TEXT,
                    event_date TEXT,
                    event_year INTEGER,
                    domain TEXT NOT NULL DEFAULT 'unknown',
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    impact_level INTEGER NOT NULL DEFAULT 3,
                    source TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_life_events_chart ON life_events(chart_id);
                CREATE INDEX IF NOT EXISTS idx_life_events_year ON life_events(event_year);
                CREATE INDEX IF NOT EXISTS idx_life_events_domain ON life_events(domain);
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL,
                    client_id TEXT,
                    summary_type TEXT NOT NULL DEFAULT 'general',
                    summary_text TEXT NOT NULL DEFAULT '',
                    key_facts_json TEXT NOT NULL DEFAULT '[]',
                    preference_json TEXT NOT NULL DEFAULT '{}',
                    source_output_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (chart_id) REFERENCES charts(chart_id) ON DELETE CASCADE
                );
            """)
            _ensure_columns(conn, 'conversation_summaries', {
                'client_id': 'TEXT',
                'summary_type': "TEXT NOT NULL DEFAULT 'general'",
                'summary_text': "TEXT NOT NULL DEFAULT ''",
                'key_facts_json': "TEXT NOT NULL DEFAULT '[]'",
                'preference_json': "TEXT NOT NULL DEFAULT '{}'",
                'source_output_ids_json': "TEXT NOT NULL DEFAULT '[]'",
                'created_at': "TEXT NOT NULL DEFAULT ''",
                'updated_at': "TEXT NOT NULL DEFAULT ''",
            })
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_summaries_chart ON conversation_summaries(chart_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_summaries_type ON conversation_summaries(summary_type)")
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


def _model_output_from_row(row):
    if not row:
        return None
    d = dict(row)
    d['structured_reasoning_json'] = _json_loads(d.get('structured_reasoning_json'), {})
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


def save_model_output(analysis_id=None, chart_id=None, client_id=None, provider=None, model=None,
                      method=None, prompt_version=None, reasoning_protocol=None, domain=None,
                      question='', input_hash='', raw_prompt='', raw_output='', parsed_answer=None,
                      structured_reasoning_json=None, latency_ms=None, token_estimate=None,
                      cost_estimate=None):
    output_id = _new_id('model_output')
    structured_reasoning_json = structured_reasoning_json if structured_reasoning_json is not None else {}
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO model_outputs (
                    id, analysis_id, chart_id, client_id, provider, model, method,
                    prompt_version, reasoning_protocol, domain, question, input_hash,
                    raw_prompt, raw_output, parsed_answer, structured_reasoning_json,
                    latency_ms, token_estimate, cost_estimate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    output_id, analysis_id, chart_id, client_id, provider, model, method,
                    prompt_version, reasoning_protocol, domain, question, input_hash,
                    raw_prompt, raw_output, parsed_answer,
                    json.dumps(structured_reasoning_json, ensure_ascii=False),
                    latency_ms, token_estimate, cost_estimate,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM model_outputs WHERE id = ?", (output_id,)).fetchone()
            return _model_output_from_row(row)
        finally:
            conn.close()


def get_model_output(output_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM model_outputs WHERE id = ?", (output_id,)).fetchone()
            return _model_output_from_row(row)
        finally:
            conn.close()


def list_model_outputs(chart_id=None, analysis_id=None, limit=50):
    try:
        limit = int(limit or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))
    sql = "SELECT * FROM model_outputs"
    conditions = []
    params = []
    if chart_id:
        conditions.append("chart_id = ?")
        params.append(chart_id)
    if analysis_id:
        conditions.append("analysis_id = ?")
        params.append(analysis_id)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [_model_output_from_row(r) for r in rows]
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


# ============================================================
# Benchmark CRUD
# ============================================================

def save_benchmark_case(id, source='internal', person_id=None, name='',
                        profile_json='{}', chart_input_json='{}', chart_result_json='{}',
                        verified_events_json='[]', anonymized=1, license_note=''):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO benchmark_cases (
                    id, source, person_id, name, profile_json, chart_input_json,
                    chart_result_json, verified_events_json, anonymized, license_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, source, person_id, name, profile_json, chart_input_json,
                 chart_result_json, verified_events_json, anonymized, license_note),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM benchmark_cases WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_benchmark_case(case_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM benchmark_cases WHERE id = ?", (case_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_benchmark_cases(source=None, limit=50):
    try:
        limit = int(limit or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))
    sql = "SELECT * FROM benchmark_cases"
    conditions = []
    params = []
    if source:
        conditions.append("source = ?")
        params.append(source)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def save_benchmark_question(id, case_id, domain='unknown', question='', options_json='[]',
                            answer='', expected_evidence_json='[]', difficulty='medium',
                            evaluator_notes=''):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO benchmark_questions (
                    id, case_id, domain, question, options_json, answer,
                    expected_evidence_json, difficulty, evaluator_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, case_id, domain, question, options_json, answer,
                 expected_evidence_json, difficulty, evaluator_notes),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM benchmark_questions WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_benchmark_question(question_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM benchmark_questions WHERE id = ?", (question_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_benchmark_questions(case_id=None, domain=None, limit=50):
    try:
        limit = int(limit or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))
    sql = "SELECT * FROM benchmark_questions"
    conditions = []
    params = []
    if case_id:
        conditions.append("case_id = ?")
        params.append(case_id)
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def save_benchmark_run(id, dataset, provider='', model='', method='structured',
                       prompt_version='', reasoning_protocol='', n_cases=0, n_questions=0,
                       accuracy=None, evidence_score=None, stability_score=None,
                       safety_score=None, report_path=''):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO benchmark_runs (
                    id, dataset, provider, model, method, prompt_version,
                    reasoning_protocol, n_cases, n_questions, accuracy,
                    evidence_score, stability_score, safety_score, report_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, dataset, provider, model, method, prompt_version,
                 reasoning_protocol, n_cases, n_questions, accuracy,
                 evidence_score, stability_score, safety_score, report_path),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM benchmark_runs WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_benchmark_run(run_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM benchmark_runs WHERE id = ?", (run_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_benchmark_runs(dataset=None, model=None, limit=20):
    try:
        limit = int(limit or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    sql = "SELECT * FROM benchmark_runs"
    conditions = []
    params = []
    if dataset:
        conditions.append("dataset = ?")
        params.append(dataset)
    if model:
        conditions.append("model = ?")
        params.append(model)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ============================================================
# Life Events CRUD
# ============================================================

def save_life_event(id, chart_id, client_id=None, event_date=None, event_year=None,
                    domain='unknown', title='', description='', impact_level=3, source='user'):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO life_events (
                    id, chart_id, client_id, event_date, event_year, domain,
                    title, description, impact_level, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, chart_id, client_id, event_date, event_year, domain,
                 title, description, impact_level, source),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM life_events WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_life_event(event_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM life_events WHERE id = ?", (event_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_life_events(chart_id, domain=None, year=None, limit=100):
    try:
        limit = int(limit or 100)
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(limit, 200))
    sql = "SELECT * FROM life_events WHERE chart_id = ?"
    params = [chart_id]
    if domain:
        sql += " AND domain = ?"
        params.append(domain)
    if year is not None:
        sql += " AND event_year = ?"
        params.append(year)
    sql += " ORDER BY event_year ASC, created_at ASC LIMIT ?"
    params.append(limit)
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def delete_life_event(event_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM life_events WHERE id = ?", (event_id,))
            conn.commit()
        finally:
            conn.close()


# ============================================================
# Conversation Summaries CRUD
# ============================================================

def save_conversation_summary(id, chart_id, client_id=None, summary_type='general',
                              summary_text='', key_facts_json='[]', preference_json='{}',
                              source_output_ids_json='[]'):
    with _conn_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO conversation_summaries (
                    id, chart_id, client_id, summary_type, summary_text,
                    key_facts_json, preference_json, source_output_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))""",
                (id, chart_id, client_id, summary_type, summary_text,
                 key_facts_json, preference_json, source_output_ids_json),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM conversation_summaries WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_conversation_summary(summary_id):
    with _conn_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM conversation_summaries WHERE id = ?", (summary_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_conversation_summaries(chart_id, summary_type=None, limit=20):
    try:
        limit = int(20 if limit is None else limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    sql = "SELECT * FROM conversation_summaries WHERE chart_id = ?"
    params = [chart_id]
    if summary_type:
        sql += " AND summary_type = ?"
        params.append(summary_type)
    sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
    params.append(limit)
    with _conn_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_latest_conversation_summary(chart_id, summary_type=None):
    items = list_conversation_summaries(chart_id=chart_id, summary_type=summary_type, limit=1)
    return items[0] if items else None


# Auto-initialize on import
init_db()
