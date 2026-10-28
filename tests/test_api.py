"""API tests that need no models or keys: validation, size limit, rate limit, samples."""

import pytest
from fastapi.testclient import TestClient

import backend.guards as guards
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate():
    guards._hits.clear()
    yield
    guards._hits.clear()


def test_samples_are_synthetic():
    r = client.get("/api/samples")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert all("SYNTHETIC SAMPLE FIR" in v for v in data.values())


def test_brief_rejects_short_input():
    r = client.post("/api/brief", json={"fir_text": "too short"})
    assert r.status_code == 422


def test_body_size_limit():
    r = client.post("/api/audit", json={"draft_text": "x" * (guards.MAX_BODY_BYTES + 10)})
    assert r.status_code == 413


def test_rate_limit_per_ip():
    codes = [client.post("/api/brief", json={"fir_text": "short"}, headers={"x-forwarded-for": "9.9.9.9"}).status_code
             for _ in range(guards.RATE_PER_MIN + 1)]
    assert codes[-1] == 429
    assert all(c == 422 for c in codes[:-1])


def test_error_responses_do_not_leak_tracebacks():
    r = client.post("/api/brief", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert "Traceback" not in r.text
