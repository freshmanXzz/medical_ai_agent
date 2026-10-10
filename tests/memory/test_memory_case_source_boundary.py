"""Shared case access does not make private discussions shared evidence."""

from martin.db import transaction
from martin.memory.namespaces import case_memory_ns
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.repositories.access import AccessRepository
from martin.services.thread_service import ThreadService


def test_shared_case_discussions_are_private_and_same_keys_do_not_overwrite(entity_db):
    service = MemoryService(entity_db)
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D002", "P001")
    thread_a = ThreadService(entity_db).create_thread("D001", "C002")
    thread_b = ThreadService(entity_db).create_thread("D002", "C002")
    service.save_case_memory(
        "D001", "C002", "discussion", {"text": "Doctor A private synthetic discussion"}
    )
    service.save_case_memory(
        "D002", "C002", "discussion", {"text": "Doctor B private synthetic discussion"}
    )
    a = service.snapshot_for_thread("D001", thread_a).case_memories
    b = service.snapshot_for_thread("D002", thread_b).case_memories
    assert a["discussion"]["text"] == "Doctor A private synthetic discussion"
    assert b["discussion"]["text"] == "Doctor B private synthetic discussion"
    assert a["discussion"]["doctor_id"] == "D001"
    assert b["discussion"]["doctor_id"] == "D002"
    assert a["discussion"]["provenance"]["kind"] == "api_submission"
    assert a["discussion"]["provenance"]["message_id"] is None
    assert (
        service.get_case_memories("D001", "C002")["discussion"]["text"]
        == a["discussion"]["text"]
    )


def test_unknown_legacy_case_source_is_retained_but_never_injected_and_trace_is_opaque(
    entity_db,
):
    service = MemoryService(entity_db)
    thread = ThreadService(entity_db).create_thread("D001", "C002")
    key = "private-key-synthetic-marker"
    raw = {"text": "Unknown doctor legacy synthetic discussion"}
    service._store().put(case_memory_ns("C002"), key, raw)
    snapshot = service.snapshot_for_thread("D001", thread)
    assert snapshot.case_memories == {}
    assert snapshot.case_memory_governance[0]["reason"] == "source_unknown"
    assert snapshot.case_memory_governance[0]["category"] == "legacy_case_memory"
    assert key not in str(snapshot.case_memory_governance)
    assert raw["text"] not in snapshot.to_prompt()
    assert service._store().get(case_memory_ns("C002"), key).value == raw
    assert service.get_case_memories("D001", "C002") == {}


def test_forged_case_provenance_cannot_expose_foreign_or_unbound_source(entity_db):
    service = MemoryService(entity_db)
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D002", "P001")
    thread = ThreadService(entity_db).create_thread("D001", "C002")
    other_thread = ThreadService(entity_db).create_thread("D002", "C002")
    service._store().put(
        case_memory_ns("C002"),
        "foreign",
        {
            "doctor_id": "D002",
            "patient_id": "P001",
            "case_id": "C002",
            "source_type": "case",
            "source_id": "C002",
            "text": "Do not expose foreign source",
            "provenance": {
                "kind": "api_submission",
                "actor_id": "D002",
                "actor_role": "doctor",
                "submission_id": "foreign",
            },
        },
    )
    service._store().put(
        case_memory_ns("C002"),
        "forged",
        {
            "doctor_id": "D001",
            "patient_id": "P001",
            "case_id": "C002",
            "source_type": "case",
            "source_id": "C002",
            "text": "Do not expose forged source",
            "provenance": {
                "kind": "message",
                "actor_id": "D001",
                "actor_role": "doctor",
                "thread_id": other_thread,
                "message_id": "forged",
            },
        },
    )
    snapshot = service.snapshot_for_thread("D001", thread)
    assert snapshot.case_memories == {}
    assert {decision["reason"] for decision in snapshot.case_memory_governance} == {
        "scope_denied",
        "source_unknown",
    }
    assert "Do not expose" not in snapshot.to_prompt()
    assert authorize_scope("D001", thread, entity_db).case_id == "C002"
