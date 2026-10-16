"""Public-demo protections: no file reads outside the web app, per-visitor sandboxes, usage limits."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import guard, store
from app.config import settings
from app.main import app

client = TestClient(app)
needs_web = pytest.mark.skipif(not (settings.web_dist / "index.html").exists(), reason="web app not built")


@needs_web
@pytest.mark.parametrize("path", [
    "/..%2fapi%2fapp%2fconfig.py", "/..%2F..%2Fetc%2Fhostname", "/%2e%2e/%2e%2e/etc/passwd",
    "/..%2F..%2Fproc%2Fself%2Fenviron", "/.env", "/assets/..%2f..%2f.env", "/..%2f..%2f..%2fservices%2fapi%2fapp%2fconfig.py",
])
def test_no_file_outside_the_web_app_is_served(path):
    r = client.get(path)
    assert r.status_code in (200, 404)
    assert "Runtime settings" not in r.text and "root:" not in r.text and "GEMINI_API_KEY" not in r.text


@needs_web
def test_real_web_files_still_served():
    assert client.get("/favicon.svg").status_code == 200
    assert "<!doctype html>" in client.get("/some/app/route").text.lower()


def test_api_docs_are_not_public():
    assert client.get("/docs").text.lower().startswith("<!doctype html>") or client.get("/docs").status_code == 404
    assert "openapi" not in client.get("/openapi.json").text.lower()


def test_security_headers():
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_visitors_cannot_see_or_delete_each_others_plans():
    a, b = {"X-Yorisoi-Session": "visitor-aaaa-1111"}, {"X-Yorisoi-Session": "visitor-bbbb-2222"}
    store.plans.put("visitor-aaaa-1111__R002", {"status": "draft", "plan": {}, "flags": [], "audit": []})
    try:
        assert client.get("/api/residents/R002", headers=a).json()["plan"] is not None
        assert client.get("/api/residents/R002", headers=b).json()["plan"] is None
        client.delete("/api/residents/R002/plan", headers=b)  # B's delete touches only B's sandbox
        assert store.plans.get("visitor-aaaa-1111__R002") is not None
    finally:
        store.plans.delete("visitor-aaaa-1111__R002")


def test_bad_session_ids_fall_back_to_public():
    for bad in ("x", "../../etc", "a" * 100, "abc def ghi"):
        assert client.get("/api/stats", headers={"X-Yorisoi-Session": bad}).status_code == 200


def test_usage_limits(monkeypatch):
    guard.reset_for_tests()
    monkeypatch.setattr(guard, "PER_VISITOR_PER_HOUR", 3)

    class Req:
        headers = {"x-yorisoi-session": "visitor-limit-0001"}
        query_params = {}
        client = None

    guard.charge(Req, 2)
    with pytest.raises(HTTPException) as e:
        guard.charge(Req, 2)
    assert e.value.status_code == 429
    guard.reset_for_tests()


def test_oversized_transcript_rejected_before_any_ai_call():
    r = client.post("/api/residents/R001/draft", json={"transcript": "あ" * (guard.MAX_TRANSCRIPT_CHARS + 1)},
                    headers={"X-Yorisoi-Session": "visitor-big-00001"})
    assert r.status_code == 413
