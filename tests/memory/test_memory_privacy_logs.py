"""Failures retain useful status without copying private exception text."""

import logging

from martin.memory.service import MemoryService
from martin.services.thread_service import ThreadService

CANARY = "synthetic-private-canary"


def _fail_with_private_text(*args, **kwargs):
    raise RuntimeError(CANARY)


def test_store_failure_log_preserves_current_fact_without_exception_text(
    entity_db, monkeypatch, caplog
):
    thread = ThreadService(entity_db).create_thread("D001", "C002")
    service = MemoryService(entity_db)
    monkeypatch.setattr(service._store(), "search", _fail_with_private_text)

    with caplog.at_level(logging.WARNING, logger="martin.memory.service"):
        snapshot = service.snapshot_for_thread("D001", thread)

    assert snapshot.available is False
    assert snapshot.error_code == "store_unavailable"
    assert snapshot.current_findings[0]["diameter_mm"] == 8
    assert snapshot.historical_observations == []
    failure = next(
        record for record in caplog.records if record.name == "martin.memory.service"
    )
    assert "RuntimeError" in failure.getMessage()
    assert failure.exc_info is None
    assert CANARY not in caplog.text


def test_websocket_failure_log_and_audit_only_receive_exception_type(
    entity_client, entity_db, monkeypatch, caplog
):
    from api.routers import agent as agent_router
    from martin.agent.audit import AuditLogger

    audit_errors = []
    monkeypatch.setattr(AuditLogger, "__init__", lambda self, **kwargs: None)
    monkeypatch.setattr(
        AuditLogger, "log_agent_error", lambda self, error: audit_errors.append(error)
    )
    monkeypatch.setattr(
        agent_router.MemoryRetrievalRouter, "retrieve", _fail_with_private_text
    )
    assert (
        entity_client.post(
            "/api/auth/login",
            json={"username": "doctor_a", "password": "TestDoctorA!2026"},
        ).status_code
        == 200
    )
    thread = ThreadService(entity_db).create_thread("D001", "C002")

    with caplog.at_level(logging.ERROR, logger="api.routers.agent"):
        with entity_client.websocket_connect(f"/api/ws/agent/{thread}") as websocket:
            assert websocket.receive_json()["type"] == "status"
            websocket.send_json({"message": "当前确认值是多少"})
            assert websocket.receive_json()["type"] == "status"
            failure = websocket.receive_json()

    assert failure["type"] == "error"
    assert CANARY not in failure["content"]
    assert audit_errors == ["RuntimeError"]
    record = next(
        record for record in caplog.records if record.name == "api.routers.agent"
    )
    assert "RuntimeError" in record.getMessage()
    assert record.exc_info is None
    assert CANARY not in caplog.text
