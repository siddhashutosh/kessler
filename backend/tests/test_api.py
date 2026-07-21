"""API contract tests via TestClient (FR-API)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:  # runs lifespan (demo pipeline refresh)
        yield test_client


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["data_mode"] == "demo"


class TestConjunctions:
    def test_list_sorted_by_urgency(self, client):
        resp = client.get("/api/v1/conjunctions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_mode"] == "demo"
        assert "Space-Track" in body["attribution"]
        events = body["events"]
        assert len(events) >= 5
        urgencies = [e["urgency"] for e in events]
        assert urgencies == sorted(urgencies, reverse=True)
        # demo data includes one CRITICAL emergency-reportable event
        assert any(e["risk"] == "CRITICAL" for e in events)

    def test_detail_and_envelope_headers(self, client):
        events = client.get("/api/v1/conjunctions").json()["events"]
        event_id = events[0]["event_id"]
        resp = client.get(f"/api/v1/conjunctions/{event_id}")
        assert resp.status_code == 200
        assert "X-Request-Id" in resp.headers
        detail = resp.json()
        assert detail["pc"]["pc_type"] in ("computed", "max", "reported")
        assert detail["action"]

    def test_unknown_event_404_envelope(self, client):
        resp = client.get("/api/v1/conjunctions/nope-404")
        assert resp.status_code == 404
        err = resp.json()["error"]
        assert err["code"] == "NOT_FOUND"
        assert err["request_id"]

    def test_insight_template_fallback(self, client):
        events = client.get("/api/v1/conjunctions").json()["events"]
        resp = client.get(f"/api/v1/conjunctions/{events[0]['event_id']}/insight")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] in ("ai", "template")
        assert len(body["briefing"]) > 40


class TestScreening:
    def test_run_screening_demo_asset(self, client):
        resp = client.post("/api/v1/screening/run", json={
            "norad_id": "61001", "window_hours": 3, "threshold_km": 25,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset"]["norad_id"] == "61001"
        assert isinstance(body["candidates"], list)

    def test_window_limit_envelope(self, client):
        resp = client.post("/api/v1/screening/run", json={
            "norad_id": "61001", "window_hours": 9999, "threshold_km": 10,
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] in ("VALIDATION_ERROR",)

    def test_unknown_asset_404(self, client):
        resp = client.post("/api/v1/screening/run", json={
            "norad_id": "99999999", "window_hours": 2, "threshold_km": 10,
        })
        assert resp.status_code == 404


class TestPipelineAndTrack:
    def test_pipeline_status_shape(self, client):
        resp = client.get("/api/v1/pipeline/status")
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        ids = {a["id"] for a in agents}
        assert {"catalog", "ingest", "parser", "pc", "risk", "publish"} <= ids
        assert all(a["status"] in ("idle", "running", "ok", "degraded", "error")
                   for a in agents)

    def test_track(self, client):
        resp = client.get("/api/v1/satellites/25544/track?minutes=30&step_s=60")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"].startswith("ISS")
        assert len(body["points"]) > 10
        first = body["points"][0]
        assert -90 <= first["lat"] <= 90
        assert 100 < first["alt_km"] < 2000

    def test_catalog_search(self, client):
        resp = client.get("/api/v1/catalog?q=ISS")
        assert resp.status_code == 200
        assert any("ISS" in row["name"] for row in resp.json())
