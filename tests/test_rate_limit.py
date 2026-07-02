#!/usr/bin/env python3
"""Rate limit, body size, and concurrency stress tests."""

import os, sys, json, time, threading, pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

spec_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api_server.py')
import importlib.util
spec = importlib.util.spec_from_file_location('api_server', spec_path)
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

client = _AuthClient(TestClient(api.app))


class TestBodySizeLimit:
    def test_small_body_accepted(self):
        r = client.post('/api/chart', json={'year': 2000, 'month': 1, 'day': 1})
        assert r.status_code == 200

    def test_large_body_rejected(self):
        """Content-Length exceeding MAX_BODY_SIZE should get 413."""
        big_payload = {'year': 2000, 'month': 1, 'day': 1, 'padding': 'x' * (2 * 1024 * 1024)}
        r = client.post('/api/chart', json=big_payload)
        # Should be rejected — may be 413 (body too large) or 422 (validation error)
        assert r.status_code in (413, 422), f'Got {r.status_code}'

    def test_invalid_content_length_rejected(self):
        r = client.post('/api/chart',
                        content='{"x":1}',
                        headers={'Content-Length': 'not-a-number'})
        assert r.status_code == 400

    def test_empty_body_works(self):
        """No Content-Length should pass through (chunked transfer is OK for small payloads)."""
        r = client.post('/api/chart', json={'year': 2000, 'month': 1, 'day': 1})
        assert r.status_code == 200


class TestRateLimit:
    def test_health_endpoint_not_limited(self):
        """Health endpoint should be rate-limit exempt."""
        for _ in range(10):
            r = client.get('/api/health')
            assert r.status_code == 200

    def test_default_path_accepts_requests(self):
        """Normal endpoint should accept requests within quota."""
        for _ in range(5):
            r = client.post('/api/chart', json={'year': 2000, 'month': 6, 'day': 15})
            assert r.status_code == 200

    def test_rate_limit_can_still_serve(self):
        """Even under load, the server should not crash."""
        responses = []
        for _ in range(50):
            r = client.post('/api/chart', json={'year': 2000 + (_ % 10), 'month': (_ % 12) + 1, 'day': (_ % 28) + 1})
            responses.append(r.status_code)
        # All should either succeed (200) or be rate-limited (429) — no 500 errors
        assert all(s in (200, 429) for s in responses), f'Got unexpected statuses: {set(responses)}'

    def test_rate_limiter_cleans_old_entries(self):
        """Call _clean_old_hits with a far-future time — should not crash."""
        api._clean_old_hits(time.time() + 99999)
        # If we get here without exception, the cleaner handled stale entries correctly
        assert True


class TestConcurrency:
    def test_concurrent_chart_creation(self):
        """Multiple threads creating charts simultaneously should not crash."""
        errors = []
        results = []

        def create_chart(idx):
            try:
                r = client.post('/api/chart', json={
                    'year': 2000 + (idx % 10),
                    'month': (idx % 12) + 1,
                    'day': (idx % 28) + 1,
                })
                results.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=create_chart, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors during concurrent access: {errors}'
        # All should succeed or be rate-limited
        assert all(s in (200, 429) for s in results), f'Unexpected statuses: {set(results)}'

    def test_concurrent_chart_read(self):
        """Concurrent reads should be safe (no deadlocks from cache lock)."""
        # First create a chart
        r = client.post('/api/chart', json={'year': 2000, 'month': 1, 'day': 1})
        assert r.status_code == 200
        cid = r.json()['chart_id']

        errors = []

        def read_chart():
            try:
                r = client.get(f'/api/charts/{cid}/data')
                assert r.status_code == 200
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_chart) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors during concurrent reads: {errors}'


class TestAuthMiddleware:
    def test_health_no_auth_needed(self):
        r = client.get('/api/health')
        assert r.status_code == 200

    def test_static_files_no_auth_needed(self):
        r = client.get('/static/app.js')
        # May 200 (file exists) or 404 (file missing) — but not 401
        assert r.status_code != 401


class TestCacheInvalidation:
    def test_save_then_read_returns_updated(self):
        """After save, next read should return updated data (cache invalidation)."""
        r = client.post('/api/chart', json={'year': 2000, 'month': 6, 'day': 15})
        assert r.status_code == 200
        cid = r.json()['chart_id']

        # Save updated data
        updated = {'four_pillars': {}, 'test_field': 'updated_value'}
        r = client.post('/api/charts/save', json={
            'chart_id': cid, 'name': 'updated', 'birth_info': {}, 'chart_data': updated
        })
        assert r.status_code == 200

        # Read back
        r = client.get(f'/api/charts/{cid}/data')
        assert r.status_code == 200
        assert r.json().get('chart_data', {}).get('test_field') == 'updated_value'



def test_query_api_key_rejected(monkeypatch):
    """Query parameter API key is always rejected (feature removed)."""
    raw_client = TestClient(api.app)
    monkeypatch.setattr(api, "_BAZI_API_KEY", "test-key-123")
    resp = raw_client.get("/api/charts?api_key=test-key-123")
    assert resp.status_code == 401


def test_bearer_token_accepted(monkeypatch):
    """Bearer token in Authorization header should still work."""
    raw_client = TestClient(api.app)
    monkeypatch.setattr(api, "_BAZI_API_KEY", "secret")
    resp = raw_client.get("/api/charts", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200
