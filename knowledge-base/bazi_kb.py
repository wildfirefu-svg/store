#!/usr/bin/env python3
"""
BaziKnowledgeBase — Unified SQLite knowledge base for BaZi analysis.
Replaces scattered JSON reads with a single indexed FTS5 database.

Usage:
    python knowledge-base/bazi_kb.py --build     # Build from JSON sources
    python knowledge-base/bazi_kb.py --stats      # Show statistics
    python knowledge-base/bazi_kb.py --search "婚姻"  # Fulltext search
"""

import argparse
import json
import os
import sqlite3

KB_DIR = os.path.dirname(os.path.abspath(__file__))

class BaziKnowledgeBase:
    """Unified knowledge base backed by SQLite + FTS5."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(KB_DIR, 'bazi_kb.db')
        self.db_path = db_path
        self.conn = None

    def _connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    # ============================================================
    # BUILD
    # ============================================================

    def build(self):
        conn = self._connect()
        self._create_schema(conn)
        self._import_gejue(conn)
        self._import_shensha(conn)
        self._import_nayin(conn)
        self._import_shishen_combos(conn)
        self._import_ziwei_patterns(conn)
        self._import_bingyao(conn)
        self._import_xiangyi(conn)
        self._import_yangzhai(conn)
        self._import_wuyun_liuqi(conn)
        conn.commit()

    def _create_schema(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS gejue;
            CREATE TABLE gejue (
                id TEXT PRIMARY KEY, category TEXT, tags TEXT,
                text TEXT, baihua TEXT, keywords TEXT
            );
            DROP TABLE IF EXISTS shensha;
            CREATE TABLE shensha (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
                type TEXT, trigger TEXT, position_meaning TEXT, intensity TEXT
            );
            DROP TABLE IF EXISTS nayin;
            CREATE TABLE nayin (
                id INTEGER PRIMARY KEY AUTOINCREMENT, gan_zhi TEXT,
                nayin TEXT, wuxing TEXT, quality_desc TEXT, prefers TEXT, avoids TEXT
            );
            DROP TABLE IF EXISTS shishen_combos;
            CREATE TABLE shishen_combos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, combo TEXT,
                gods TEXT, career TEXT, wealth TEXT, marriage TEXT,
                health TEXT, condition TEXT, example TEXT
            );
            DROP TABLE IF EXISTS ziwei_patterns;
            CREATE TABLE ziwei_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_name TEXT,
                stars TEXT, palace TEXT, meaning TEXT
            );
            DROP TABLE IF EXISTS bingyao;
            CREATE TABLE bingyao (
                id INTEGER PRIMARY KEY AUTOINCREMENT, disease TEXT,
                symptom TEXT, medicine TEXT, examples TEXT
            );
            DROP TABLE IF EXISTS xiangyi;
            CREATE TABLE xiangyi (
                id INTEGER PRIMARY KEY AUTOINCREMENT, gan_or_zhi TEXT,
                category TEXT, meaning TEXT
            );
            DROP TABLE IF EXISTS yangzhai;
            CREATE TABLE yangzhai (
                id INTEGER PRIMARY KEY AUTOINCREMENT, problem TEXT,
                solution TEXT, principle TEXT
            );
            DROP TABLE IF EXISTS wuyun_liuqi;
            CREATE TABLE wuyun_liuqi (
                id INTEGER PRIMARY KEY AUTOINCREMENT, gan_or_zhi TEXT,
                category TEXT, description TEXT
            );
            DROP TABLE IF EXISTS gejue_fts;
            CREATE VIRTUAL TABLE gejue_fts USING fts5(
                id, text, baihua, keywords,
                content='gejue', content_rowid='rowid'
            );
        """)

    def _load_json(self, filename):
        path = os.path.join(KB_DIR, filename)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _import_gejue(self, conn):
        data = self._load_json('gejue.json')
        if not data:
            return
        entries = data.get('entries', [])
        for e in entries:
            tags = e.get('tags', [])
            tags_str = json.dumps(tags, ensure_ascii=False) if isinstance(tags, list) else str(tags)
            kw = e.get('keywords', '')
            if not kw and isinstance(tags, list):
                kw = ' '.join(str(t) for t in tags)
            conn.execute(
                "INSERT OR REPLACE INTO gejue (id, category, tags, text, baihua, keywords) VALUES (?,?,?,?,?,?)",
                (e['id'], e.get('category',''), tags_str, e.get('text',''), e.get('baihua',''), kw)
            )
        conn.execute("INSERT INTO gejue_fts(rowid, id, text, baihua, keywords) SELECT rowid, id, text, baihua, keywords FROM gejue")

    def _import_shensha(self, conn):
        data = self._load_json('shensha.json')
        if not data:
            return
        for e in data.get('entries', []):
            conn.execute(
                "INSERT INTO shensha (name, type, trigger, position_meaning, intensity) VALUES (?,?,?,?,?)",
                (e['name'], e.get('type',''), json.dumps(e.get('trigger',{}), ensure_ascii=False),
                 json.dumps(e.get('position_meaning',{}), ensure_ascii=False),
                 json.dumps(e.get('intensity',{}), ensure_ascii=False))
            )

    def _import_nayin(self, conn):
        data = self._load_json('nayin.json')
        if not data:
            return
        for e in data.get('entries', []):
            q = e.get('quality', {})
            conn.execute(
                "INSERT INTO nayin (gan_zhi, nayin, wuxing, quality_desc, prefers, avoids) VALUES (?,?,?,?,?,?)",
                (e['gan_zhi'], e['nayin'], e.get('wuxing',''),
                 q.get('desc','') if isinstance(q,dict) else str(q),
                 q.get('prefers','') if isinstance(q,dict) else '',
                 q.get('avoids','') if isinstance(q,dict) else '')
            )

    def _import_shishen_combos(self, conn):
        data = self._load_json('shishen-combos.json')
        if not data:
            return
        for e in data.get('combinations', []):
            m = e.get('meaning', {})
            conn.execute(
                "INSERT INTO shishen_combos (combo, gods, career, wealth, marriage, health, condition, example) VALUES (?,?,?,?,?,?,?,?)",
                (e['combo'], e.get('gods',''),
                 m.get('career','') if isinstance(m,dict) else str(m),
                 m.get('wealth','') if isinstance(m,dict) else '',
                 m.get('marriage','') if isinstance(m,dict) else '',
                 m.get('health','') if isinstance(m,dict) else '',
                 e.get('condition',''), e.get('example',''))
            )

    def _import_ziwei_patterns(self, conn):
        data = self._load_json('ziwei-patterns.json')
        if not data:
            return
        entries = data.get('entries', data.get('patterns', []))
        for e in entries:
            conn.execute(
                "INSERT INTO ziwei_patterns (pattern_name, stars, palace, meaning) VALUES (?,?,?,?)",
                (e.get('pattern_name', e.get('name','')), json.dumps(e.get('stars',e.get('star_combo',[])), ensure_ascii=False),
                 e.get('palace',''), e.get('meaning', e.get('interpretation','')))
            )

    def _import_bingyao(self, conn):
        data = self._load_json('bingyao.json')
        if not data:
            return
        for e in data.get('entries', []):
            conn.execute(
                "INSERT INTO bingyao (disease, symptom, medicine, examples) VALUES (?,?,?,?)",
                (e['disease'], e.get('symptom',''),
                 json.dumps(e.get('medicine',{}), ensure_ascii=False) if isinstance(e.get('medicine'), dict) else str(e.get('medicine','')),
                 json.dumps(e.get('examples',[]), ensure_ascii=False) if isinstance(e.get('examples'), list) else str(e.get('examples','')))
            )

    def _import_xiangyi(self, conn):
        data = self._load_json('xiangyi.json')
        if not data:
            return
        # 天干象意
        for e in data.get('tiangan', []):
            img = e.get('imagery', {})
            meaning_text = json.dumps(img, ensure_ascii=False) if isinstance(img, dict) else str(img)
            conn.execute(
                "INSERT INTO xiangyi (gan_or_zhi, category, meaning) VALUES (?,?,?)",
                (e['gan'], '天干', meaning_text)
            )
        # 地支象意
        for e in data.get('dizhi', []):
            img = e.get('imagery', {})
            meaning_text = json.dumps(img, ensure_ascii=False) if isinstance(img, dict) else str(img)
            conn.execute(
                "INSERT INTO xiangyi (gan_or_zhi, category, meaning) VALUES (?,?,?)",
                (e['zhi'], '地支', meaning_text)
            )

    def _import_yangzhai(self, conn):
        data = self._load_json('yangzhai.json')
        if not data:
            return
        for rule in data.get('rules', []):
            conn.execute(
                "INSERT INTO yangzhai (problem, solution, principle) VALUES (?,?,?)",
                (rule.get('problem',''), rule.get('solution',''), rule.get('principle',''))
            )

    def _import_wuyun_liuqi(self, conn):
        data = self._load_json('wuyun-liuqi.json')
        if not data:
            return
        for e in data.get('wuyun', []):
            conn.execute(
                "INSERT INTO wuyun_liuqi (gan_or_zhi, category, description) VALUES (?,?,?)",
                (e.get('year_gan',''), '五运', json.dumps(e, ensure_ascii=False))
            )
        for e in data.get('liuqi', []):
            conn.execute(
                "INSERT INTO wuyun_liuqi (gan_or_zhi, category, description) VALUES (?,?,?)",
                (e.get('year_zhi',''), '六气', json.dumps(e, ensure_ascii=False))
            )

    # ============================================================
    # QUERY API
    # ============================================================

    def search_gejue(self, query, category=None, top_n=5):
        conn = self._connect()
        if category:
            rows = conn.execute(
                "SELECT * FROM gejue WHERE category=? AND (text LIKE ? OR keywords LIKE ?) LIMIT ?",
                (category, f'%{query}%', f'%{query}%', top_n)
            ).fetchall()
        else:
            try:
                rows = conn.execute(
                    "SELECT g.* FROM gejue g INNER JOIN (SELECT rowid, rank FROM gejue_fts WHERE gejue_fts MATCH ? ORDER BY rank LIMIT ?) f ON g.rowid = f.rowid",
                    (query, top_n)
                ).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(
                    "SELECT * FROM gejue WHERE text LIKE ? OR keywords LIKE ? LIMIT ?",
                    (f'%{query}%', f'%{query}%', top_n)
                ).fetchall()
        return [dict(r) for r in rows]

    def search_shensha(self, name):
        conn = self._connect()
        r = conn.execute("SELECT * FROM shensha WHERE name LIKE ? LIMIT 1", (f'%{name}%',)).fetchone()
        return dict(r) if r else None

    def search_nayin(self, gan, zhi):
        conn = self._connect()
        r = conn.execute("SELECT * FROM nayin WHERE gan_zhi=? LIMIT 1", (gan+zhi,)).fetchone()
        return dict(r) if r else None

    def search_shishen_combo(self, combo_name, top_n=5):
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM shishen_combos WHERE combo LIKE ? LIMIT ?",
            (f'%{combo_name}%', top_n)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_bingyao(self, query, top_n=5):
        conn = self._connect()
        q = f'%{query}%'
        rows = conn.execute(
            "SELECT * FROM bingyao WHERE disease LIKE ? OR symptom LIKE ? LIMIT ?",
            (q, q, top_n)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_xiangyi(self, gan_or_zhi, top_n=10):
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM xiangyi WHERE gan_or_zhi LIKE ? LIMIT ?",
            (f'%{gan_or_zhi}%', top_n)
        ).fetchall()
        return [dict(r) for r in rows]

    def fulltext_search(self, text, top_n=10):
        gejue = self.search_gejue(text, top_n=top_n)
        results = list(gejue)
        if len(results) < top_n:
            bingyao = self.search_bingyao(text, top_n=top_n-len(results))
            for b in bingyao:
                b['_source'] = 'bingyao'
                results.append(b)
        return results[:top_n]

    def stats(self):
        conn = self._connect()
        tables = ['gejue','shensha','nayin','shishen_combos','ziwei_patterns','bingyao','xiangyi','yangzhai','wuyun_liuqi']
        st = {}
        for t in tables:
            try:
                st[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                st[t] = 0
        return st


# ============================================================
# CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description='BaziKnowledgeBase CLI')
    ap.add_argument('--build', action='store_true', help='Build database from JSON sources')
    ap.add_argument('--db', default=None, help='Database path')
    ap.add_argument('--stats', action='store_true', help='Show statistics')
    ap.add_argument('--search', help='Fulltext search query')
    args = ap.parse_args()

    kb = BaziKnowledgeBase(db_path=args.db)

    if args.build:
        kb.build()
        print(f'Built: {kb.db_path}')
        for t, c in kb.stats().items():
            print(f'  {t}: {c}')
    elif args.stats:
        for t, c in kb.stats().items():
            print(f'{t}: {c}')
    elif args.search:
        results = kb.fulltext_search(args.search)
        for i, r in enumerate(results):
            text = r.get('text', str(r)[:120])
            print(f'{i+1}. {text[:120]}')
    else:
        ap.print_help()

    kb.close()

if __name__ == '__main__':
    main()
