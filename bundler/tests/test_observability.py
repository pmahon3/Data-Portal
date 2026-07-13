"""Ops surfaces mounted by the hand-owned observability entry (not OpenAPI)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from bundler_server.observability.app import app


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests" in body or "python_info" in body or "# HELP" in body
    assert "bundler_worker_count" in body
    assert "bundler_jobs" in body


def test_actuator_live_and_info() -> None:
    client = TestClient(app)
    live = client.get("/actuator/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "UP"

    info = client.get("/actuator/info")
    assert info.status_code == 200
    body = info.json()
    assert "app" in body
    assert "bundler" in body
    assert "workerCount" in body["bundler"]


def test_actuator_ready_reports_queue_details() -> None:
    client = TestClient(app)
    ready = client.get("/actuator/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "UP"
    assert "details" in body
    assert "queuedJobs" in body["details"]
    assert "queueMaxSize" in body["details"]


def test_product_health_still_works() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
