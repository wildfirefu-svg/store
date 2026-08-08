#!/usr/bin/env python3
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

spec = importlib.util.spec_from_file_location('api_server', 'api_server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

from fastapi.testclient import TestClient

_API_KEY = getattr(api, '_BAZI_API_KEY', '')
_AUTH_HEADERS = {'Authorization': f'Bearer {_API_KEY}'} if _API_KEY else {}


class _AuthClient:
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

    def put(self, url, **kw):
        kw['headers'] = self._h(kw.get('headers'))
        return self._c.put(url, **kw)

    def delete(self, url, **kw):
        kw['headers'] = self._h(kw.get('headers'))
        return self._c.delete(url, **kw)


client = _AuthClient(TestClient(api.app))


def _create_chart():
    r = client.post('/api/chart', json={'year': 1990, 'month': 5, 'day': 12, 'hour': 8, 'gender': 'male'})
    assert r.status_code == 200
    return r.json()['chart_id']


def test_clients_crud_api():
    r = client.post('/api/clients', json={'name': 'API客户', 'gender': 'male', 'tags': ['事业']})
    assert r.status_code == 200
    data = r.json()
    client_id = data['id']
    try:
        assert data['name'] == 'API客户'
        assert data['tags'] == ['事业']

        r = client.get('/api/clients?search=API客户')
        assert r.status_code == 200
        assert any(c['id'] == client_id for c in r.json()['clients'])

        r = client.get(f'/api/clients/{client_id}')
        assert r.status_code == 200
        assert r.json()['name'] == 'API客户'

        r = client.put(f'/api/clients/{client_id}', json={'name': 'API客户更新', 'tags': ['事业', 'VIP']})
        assert r.status_code == 200
        assert r.json()['name'] == 'API客户更新'
        assert r.json()['tags'] == ['事业', 'VIP']
    finally:
        r = client.delete(f'/api/clients/{client_id}')
        assert r.status_code == 200


def test_client_chart_analysis_feedback_api():
    chart_id = _create_chart()
    r = client.post('/api/clients', json={'name': '关联API客户'})
    assert r.status_code == 200
    client_id = r.json()['id']
    try:
        r = client.post(f'/api/clients/{client_id}/charts/{chart_id}')
        assert r.status_code == 200

        r = client.get(f'/api/clients/{client_id}/charts')
        assert r.status_code == 200
        assert any(c['chart_id'] == chart_id for c in r.json()['charts'])

        analysis = api.data_store.save_analysis(
            client_id=client_id,
            chart_id=chart_id,
            analysis_type='chat',
            topic='sihechu',
            question='测试问题',
            ai_text='测试回答',
        )

        r = client.get(f'/api/clients/{client_id}/analyses')
        assert r.status_code == 200
        assert any(a['id'] == analysis['id'] for a in r.json()['analyses'])

        r = client.get(f'/api/charts/{chart_id}/analyses')
        assert r.status_code == 200
        assert any(a['id'] == analysis['id'] for a in r.json()['analyses'])

        r = client.get(f'/api/analyses/{analysis["id"]}')
        assert r.status_code == 200
        assert r.json()['id'] == analysis['id']

        r = client.post(f'/api/analyses/{analysis["id"]}/feedback', json={
            'dimension': 'career',
            'judgment_text': '适合专业路线',
            'is_accurate': True,
            'user_comment': '准确',
        })
        assert r.status_code == 200
        assert r.json()['dimension'] == 'career'

        r = client.get('/api/feedback/stats')
        assert r.status_code == 200
        assert 'dimension_accuracy' in r.json()
    finally:
        client.delete(f'/api/clients/{client_id}')
