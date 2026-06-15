#!/usr/bin/env python3
import os
import sys
import importlib.util

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

    def get(self, url, **kw):
        if _AUTH_HEADERS:
            kw['headers'] = {**kw.get('headers', {}), **_AUTH_HEADERS}
        return self._c.get(url, **kw)

    def post(self, url, **kw):
        if _AUTH_HEADERS:
            kw['headers'] = {**kw.get('headers', {}), **_AUTH_HEADERS}
        return self._c.post(url, **kw)


client = _AuthClient(TestClient(api.app))


def test_chart_visualization_api_shape():
    r = client.post('/api/chart', json={'year': 1990, 'month': 5, 'day': 12, 'hour': 8, 'gender': 'male'})
    assert r.status_code == 200
    chart_id = r.json()['chart_id']

    r = client.get(f'/api/charts/{chart_id}/visualization')
    assert r.status_code == 200
    data = r.json()

    assert set(['wuxing', 'shishen', 'dayun', 'liunian']).issubset(data.keys())
    assert set(['金', '木', '水', '火', '土']).issubset(data['wuxing'].keys())
    assert isinstance(data['shishen'], dict)
    assert isinstance(data['dayun'], list)
    assert isinstance(data['liunian'], list)
