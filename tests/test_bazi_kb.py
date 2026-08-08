#!/usr/bin/env python3
"""Tests for BaziKnowledgeBase — SQLite knowledge base."""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'knowledge-base'))

spec = importlib.util.spec_from_file_location('bazi_kb', 'knowledge-base/bazi_kb.py')
bazi_kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bazi_kb)
BaziKnowledgeBase = bazi_kb.BaziKnowledgeBase

TEST_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'knowledge-base', '_test_bazi_kb.db')


@pytest.fixture(scope='module')
def kb():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    k = BaziKnowledgeBase(db_path=TEST_DB)
    k.build()
    yield k
    k.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


class TestBuildAndStats:
    def test_db_created(self, kb):
        assert os.path.exists(TEST_DB)

    def test_stats_gejue(self, kb):
        s = kb.stats()
        assert s['gejue'] >= 900

    def test_stats_shensha(self, kb):
        s = kb.stats()
        assert s['shensha'] >= 70

    def test_stats_nayin(self, kb):
        s = kb.stats()
        assert s['nayin'] >= 50

    def test_stats_combos(self, kb):
        s = kb.stats()
        assert s['shishen_combos'] >= 1000

    def test_stats_all_tables_nonzero(self, kb):
        s = kb.stats()
        assert all(v > 0 for v in s.values()), f'empty tables: {[k for k,v in s.items() if v==0]}'


class TestGejueSearch:
    def test_search_marriage(self, kb):
        results = kb.search_gejue('婚姻')
        assert len(results) > 0

    def test_search_by_category(self, kb):
        results = kb.search_gejue('财', category='财官断诀')
        assert len(results) > 0

    def test_search_nonexistent(self, kb):
        results = kb.search_gejue('xyzabc123不存在')
        assert len(results) == 0

    def test_search_top_n(self, kb):
        results = kb.search_gejue('婚姻', top_n=3)
        assert len(results) <= 3

    def test_results_have_fields(self, kb):
        results = kb.search_gejue('婚姻', top_n=1)
        r = results[0]
        assert 'text' in r
        assert 'category' in r
        assert 'id' in r


class TestSpecializedSearch:
    def test_shensha_lookup(self, kb):
        r = kb.search_shensha('天乙贵人')
        assert r is not None
        assert '天乙' in r.get('name', '')

    def test_nayin_lookup(self, kb):
        r = kb.search_nayin('甲', '子')
        assert r is not None
        assert r['nayin'] == '海中金'

    def test_nayin_all_60(self, kb):
        combos = [('甲','子'),('丙','寅'),('戊','辰'),('庚','午'),('壬','申'),
                  ('乙','亥'),('丁','卯'),('己','巳'),('辛','未'),('癸','酉')]
        for gan, zhi in combos:
            r = kb.search_nayin(gan, zhi)
            assert r is not None, f'missing nayin for {gan}{zhi}'

    def test_shishen_combo(self, kb):
        results = kb.search_shishen_combo('官印相生')
        assert len(results) > 0

    def test_bingyao_search(self, kb):
        results = kb.search_bingyao('财多')
        assert len(results) > 0

    def test_xiangyi_search(self, kb):
        results = kb.search_xiangyi('甲')
        assert len(results) > 0

    def test_shensha_nonexistent(self, kb):
        r = kb.search_shensha('不存在的煞')
        assert r is None


class TestFulltext:
    def test_fulltext_marriage(self, kb):
        results = kb.fulltext_search('婚姻')
        assert len(results) > 0

    def test_fulltext_wealth(self, kb):
        results = kb.fulltext_search('财运')
        assert len(results) > 0


class TestCLI:
    def test_build_cli(self):
        db = TEST_DB + '.cli'
        if os.path.exists(db):
            os.remove(db)
        ret = os.system(f'python knowledge-base/bazi_kb.py --build --db {db}')
        assert ret == 0
        assert os.path.exists(db)
        os.remove(db)

    def test_stats_cli(self):
        ret = os.system('python knowledge-base/bazi_kb.py --stats')
        assert ret == 0

    def test_search_cli(self):
        ret = os.system('python knowledge-base/bazi_kb.py --search 婚姻')
        assert ret == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
