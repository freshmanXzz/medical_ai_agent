"""Core governance regression probes against real isolated SQLite stores."""

import sqlite3

import pytest
from pydantic import ValidationError

from martin.memory.lifecycle import normalize_provenance
from martin.memory.models import MemoryCandidate
from martin.memory.namespaces import doctor_preferences_ns, doctor_records_ns
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.memory.store import close_default_store
from martin.memory.tools import save_long_term_memory
from martin.memory.writer import MemoryWriter
from martin.services.thread_service import ThreadService


def _scope(db):
    thread = ThreadService(db).create_thread("D001", "C002")
    return authorize_scope("D001", thread, db)


def _source(scope):
    return {
        "kind": "api_submission",
        "actor_id": scope.doctor_id,
        "actor_role": "doctor",
        "thread_id": scope.thread_id,
        "submission_id": "synthetic-review-submission",
    }


def test_bare_v1_preference_can_be_retracted_without_resurrection(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    service._store().put(
        doctor_preferences_ns("D001"), "report_style", {"max_words": 200}
    )
    record = service.list_records(scope)[0]
    assert record["memory_id"] == "legacy:preference:report_style"
    assert record["provenance"]["kind"] == "legacy_unknown"
    assert service.get_doctor_preferences("D001") == {
        "report_style": {"max_words": 200}
    }
    service.retract_record(scope, record["memory_id"], provenance=_source(scope))
    service._store().put(
        doctor_preferences_ns("D001"), "report_style", {"max_words": 200}
    )
    close_default_store()
    assert service.get_doctor_preferences("D001") == {}
    assert service.list_records(scope) == []
    assert (
        service.record_history(scope, record["memory_id"])[0]["status"] == "retracted"
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"reasoning": "unsupported secret deliberation"},
        {"max_words": 200, "status": "retracted"},
        {"max_words": 200, "valid_until": "2024-01-01"},
    ],
)
def test_invalid_bare_v1_preference_has_no_raw_fallback(entity_db, raw):
    service = MemoryService(entity_db)
    service._store().put(doctor_preferences_ns("D001"), "report_style", raw)
    assert service.get_doctor_preferences("D001") == {}


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "legacy_unknown", "actor_role": "assistant"},
        {"kind": "legacy_unknown", "actor_id": "D002"},
        {"kind": "legacy_unknown", "message_id": "fabricated"},
        {"kind": "api_submission", "submission_id": "s", "reasoning": "private"},
    ],
)
def test_provenance_cannot_launder_assistant_or_unknown_message(change):
    source = {"actor_id": "D001", "actor_role": "doctor", **change}
    with pytest.raises(ValueError):
        normalize_provenance(source, doctor_id="D001")


def test_corrupt_current_preference_does_not_revive_raw_projection(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_source(scope)
    )
    record["interaction_id"] = "fabricated-message-for-api-submission"
    service._store().put(doctor_records_ns("D001"), record["memory_id"], record)
    assert service.get_doctor_preferences("D001") == {}
    assert service.list_records(scope) == []


@pytest.mark.parametrize("identity", [None, "", "missing"])
def test_damaged_preference_identity_does_not_revive_legacy_projection(
    entity_db, identity
):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_source(scope)
    )
    if identity == "missing":
        record.pop("logical_key")
    else:
        record["logical_key"] = identity
    service._store().put(doctor_records_ns("D001"), record["memory_id"], record)
    close_default_store()
    assert service.get_doctor_preferences("D001") == {}
    assert service.list_records(scope) == []


def test_sqlite_statement_failure_rolls_back_projection_and_record(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_source(scope)
    )
    store = service._store()
    # SqliteStore issues projection DELETE before its INSERT/REPLACE statement.
    # Abort the latter so this checks a real partial SQL execution, not a mock
    # that fails before the transaction starts.
    store.conn.execute("""
        CREATE TRIGGER fail_governance_insert BEFORE INSERT ON store
        WHEN NEW.key != 'report_style'
        BEGIN SELECT RAISE(ABORT, 'synthetic second statement failure'); END
    """)
    store.conn.commit()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="second statement"):
            service.retract_record(
                scope, record["memory_id"], provenance=_source(scope)
            )
    finally:
        store.conn.execute("DROP TRIGGER fail_governance_insert")
        store.conn.commit()
    close_default_store()
    assert service.get_record(scope, record["memory_id"])["status"] == "active"
    assert service._store().get(
        doctor_preferences_ns("D001"), "report_style"
    ).value == {"max_words": 200}
    assert len(service.record_history(scope, record["memory_id"])) == 1


def test_revision_retry_still_validates_provenance_and_reason(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    writer = MemoryWriter(service)
    original = writer.write(
        scope,
        [MemoryCandidate("task_followup", "等待资料", "task")],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=_source(scope),
    ).records[0]
    candidate = MemoryCandidate("task_followup", "等待复核")
    replacement = writer.revise(
        scope, original["memory_id"], candidate, provenance=_source(scope)
    ).records[0]
    assert (
        writer.revise(
            scope, original["memory_id"], candidate, provenance=_source(scope)
        ).records[0]["memory_id"]
        == replacement["memory_id"]
    )
    with pytest.raises(ValueError):
        writer.revise(
            scope,
            original["memory_id"],
            candidate,
            provenance=dict(_source(scope), actor_role="assistant"),
        )
    with pytest.raises(ValueError):
        writer.revise(
            scope,
            original["memory_id"],
            candidate,
            reason="x" * 501,
            provenance=_source(scope),
        )


def test_confidence_only_revision_is_saved_and_retry_is_idempotent(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    writer = MemoryWriter(service)
    original = writer.write(
        scope,
        [MemoryCandidate("clinical_claim", "待核实陈述", "claim", confidence=0.9)],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=_source(scope),
    ).records[0]
    candidate = MemoryCandidate("clinical_claim", "待核实陈述", confidence=0.4)
    revised = writer.revise(
        scope, original["memory_id"], candidate, provenance=_source(scope)
    ).records[0]
    assert revised["memory_id"] != original["memory_id"]
    assert revised["confidence"] == 0.4
    assert revised["verification_status"] == "unverified"
    close_default_store()
    assert service.get_record(scope, revised["memory_id"])["confidence"] == 0.4
    assert (
        writer.revise(
            scope, original["memory_id"], candidate, provenance=_source(scope)
        ).records[0]["memory_id"]
        == revised["memory_id"]
    )


def test_expired_target_cannot_be_revised_or_used_as_active_retry(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    writer = MemoryWriter(service)
    expired = writer.write(
        scope,
        [
            MemoryCandidate(
                "task_followup", "过期待办", "task", valid_until="2024-01-01"
            )
        ],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=_source(scope),
    ).records[0]
    assert service.get_record(scope, expired["memory_id"]) is None
    with pytest.raises(ValueError, match="active memory"):
        writer.revise(
            scope,
            expired["memory_id"],
            MemoryCandidate("task_followup", "新待办"),
            provenance=_source(scope),
        )
    retracted = service.retract_record(
        scope, expired["memory_id"], provenance=_source(scope)
    )
    assert retracted["status"] == "retracted"


def test_authored_claim_cannot_claim_business_event_provenance(entity_db):
    scope = _scope(entity_db)
    with pytest.raises(ValueError, match="business event"):
        MemoryWriter(MemoryService(entity_db)).write(
            scope,
            [MemoryCandidate("clinical_claim", "尚待核实的医生陈述")],
            source_type="thread",
            source_id=scope.thread_id,
            provenance={
                "kind": "business_event",
                "actor_id": "D001",
                "actor_role": "doctor",
            },
        )


def test_agent_tool_does_not_coerce_boolean_finding_value_to_measurement():
    with pytest.raises(ValidationError):
        save_long_term_memory.args_schema.model_validate(
            {
                "memory_type": "correction",
                "text": "待核实直径",
                "target_finding_id": "F002",
                "field": "diameter_mm",
                "proposed_value": True,
            }
        )
