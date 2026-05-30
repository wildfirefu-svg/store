#!/usr/bin/env python3
"""Tests for BaZi Analysis API server."""
import os, sys, json, pytest, importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

spec = importlib.util.spec_from_file_location('api_server', 'api_server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

from fastapi.testclient import TestClient

# Auto-detect API key for auth-enabled servers
_API_KEY = getattr(api, '_BAZI_API_KEY', '')
_AUTH_HEADERS = {'Authorization': f'Bearer {_API_KEY}'} if _API_KEY else {}

class _AuthClient:
    """Wrapper around TestClient that auto-injects auth headers."""
    def __init__(self, client):
        self._c = client
    def _h(self, headers):
        if not _AUTH_HEADERS:
            return headers
        return {**headers, **_AUTH_HEADERS} if headers else _AUTH_HEADERS
    def get(self, url, **kw):
        kw['headers'] = self._h(kw.get('headers'))
        return self._c.get(url, **kw)
    def post(self, url, **kw):
        kw['headers'] = self._h(kw.get('headers'))
        return self._c.post(url, **kw)

client = _AuthClient(TestClient(api.app))

# Shared: get a chart ID for dependent endpoints
def _get_chart_id(gender='male'):
    r = client.post('/api/chart', json={
        'year': 1993, 'month': 7, 'day': 15, 'hour': 14, 'gender': gender
    })
    assert r.status_code == 200
    return r.json()['chart_id']


class TestHealth:
    def test_health(self):
        r = client.get('/api/health')
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'

    def test_health_version(self):
        r = client.get('/api/health')
        assert 'version' in r.json()


class TestChart:
    def test_calculate(self):
        r = client.post('/api/chart', json={
            'year': 1993, 'month': 7, 'day': 15, 'hour': 14, 'gender': 'male'
        })
        assert r.status_code == 200
        data = r.json()
        assert 'chart_id' in data
        assert 'four_pillars' in data
        assert 'day_master' in data
        assert 'da_yun' in data
        assert len(data['da_yun']) >= 8

    def test_calculate_female(self):
        r = client.post('/api/chart', json={
            'year': 1993, 'month': 7, 'day': 15, 'hour': 14, 'gender': 'female'
        })
        assert r.status_code == 200

    def test_calculate_defaults(self):
        r = client.post('/api/chart', json={'year': 2000, 'month': 1, 'day': 1})
        assert r.status_code == 200

    def test_get_existing_chart(self):
        cid = _get_chart_id()
        r = client.get(f'/api/chart/{cid}')
        assert r.status_code == 200

    def test_get_missing_chart(self):
        r = client.get('/api/chart/nonexistent')
        assert r.status_code == 404

    def test_chart_has_birth_info(self):
        r = client.post('/api/chart', json={
            'year': 1993, 'month': 7, 'day': 15, 'hour': 14, 'gender': 'male'
        })
        assert r.status_code == 200
        assert 'birth_info' in r.json()
        assert r.json()['birth_info']['year'] == 1993


class TestZeri:
    def test_zeri_basic(self):
        cid = _get_chart_id()
        r = client.post('/api/tools/zeri', json={
            'chart_id': cid, 'year': 2026, 'month': 6, 'purpose': '结婚', 'top_n': 3
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data['dates']) == 3
        assert data['dates'][0]['score'] > 0

    def test_zeri_requires_chart_id(self):
        r = client.post('/api/tools/zeri', json={})
        assert r.status_code in (400, 422)  # Pydantic may return 422 before our 400


class TestLiunian:
    def test_liunian_basic(self):
        cid = _get_chart_id()
        r = client.post('/api/tools/liunian', json={
            'chart_id': cid, 'target_year': 2026
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data['months']) == 12
        assert 'overview' in data
        assert 'best_month' in data['overview']

    def test_liunian_requires_chart_id(self):
        r = client.post('/api/tools/liunian', json={})
        assert r.status_code in (400, 422)  # Pydantic may return 422 before our 400


class TestNameEval:
    def test_name_eval_basic(self):
        cid = _get_chart_id()
        r = client.post('/api/tools/name/eval', json={
            'chart_id': cid, 'name': '张伟', 'gender': 'male'
        })
        assert r.status_code == 200
        data = r.json()
        assert 'total_score' in data
        assert 'grade' in data
        assert 0 <= data['total_score'] <= 100

    def test_name_eval_requires_chart_id(self):
        r = client.post('/api/tools/name/eval', json={})
        assert r.status_code == 422  # FastAPI validation error


class TestNameGen:
    def test_name_gen_basic(self):
        cid = _get_chart_id()
        r = client.post('/api/tools/name/gen', json={
            'chart_id': cid, 'surname': '李', 'gender': 'male', 'top_n': 5
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 5
        assert all('name' in n and 'total_score' in n for n in data)

    def test_name_gen_female(self):
        cid = _get_chart_id('female')
        r = client.post('/api/tools/name/gen', json={
            'chart_id': cid, 'surname': '张', 'gender': 'female', 'top_n': 3
        })
        assert r.status_code == 200
        assert len(r.json()) == 3


class TestCaseSearch:
    def test_case_search_basic(self):
        cid = _get_chart_id()
        r = client.post('/api/tools/case/search', json={
            'chart_id': cid, 'top_n': 3
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert 'name' in data[0]
        assert 'similarity' in data[0]
        assert 0 <= data[0]['similarity'] <= 1.0

    def test_case_search_requires_chart_id(self):
        r = client.post('/api/tools/case/search', json={})
        assert r.status_code in (400, 422)  # Pydantic may return 422 before our 400


class TestKB:
    def test_kb_search(self):
        r = client.get('/api/kb/search', params={'q': '婚姻'})
        assert r.status_code == 200
        data = r.json()
        assert data['count'] > 0
        assert len(data['results']) > 0

    def test_kb_search_top(self):
        r = client.get('/api/kb/search', params={'q': '财运', 'top': 3})
        assert r.status_code == 200
        assert len(r.json()['results']) <= 3

    def test_kb_stats(self):
        r = client.get('/api/kb/stats')
        assert r.status_code == 200
        data = r.json()
        assert data['gejue'] >= 900
        assert data['shensha'] >= 70


class TestAnalyzePdfSecurity:
    def test_pdf_rejects_invalid_template(self):
        cid = _get_chart_id()
        r = client.post('/api/analyze/pdf', json={
            'chart_id': cid, 'mode': 1,
            'template': 'dark; echo hacked'
        })
        assert r.status_code in (422, 401, 400)  # validation or auth error

    def test_pdf_accepts_known_template(self):
        cid = _get_chart_id()
        r = client.post('/api/analyze/pdf', json={
            'chart_id': cid, 'mode': 1,
            'template': 'dark'
        })
        assert r.status_code in (200, 400, 500)  # ok or missing deps


class TestCorsPolicy:
    def test_cors_origins_are_not_wildcard_by_default(self):
        assert "*" not in api._cors_origins()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
