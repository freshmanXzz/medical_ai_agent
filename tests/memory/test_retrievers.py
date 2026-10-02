"""Authorized exact records and deterministic temporal business projections."""

import json
from dataclasses import replace

import pytest
from langgraph.store.sqlite import SqliteStore

from martin.db import transaction
from martin.memory.retrievers import ExactRetriever, TemporalRetriever
from martin.memory.scope import MemoryScope, authorize_scope, revalidate_scope
from martin.memory.service import MemoryService
from martin.repositories.access import AccessRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.threads import ThreadRepository
from martin.repositories.users import UserRepository
from martin.services.access_service import AccessDeniedError, EntityNotFoundError


@pytest.fixture
def scope(entity_db):
    with transaction(entity_db) as connection:
        thread_id = ThreadRepository(connection).create("D001", "C002")
    return authorize_scope("D001", thread_id, entity_db)


def _finding(db_path, finding_id, case_id, observed_at, diameter, **kwargs):
    with transaction(db_path) as connection:
        FindingRepository(connection).create(
            case_id,
            "nodule",
            observed_at,
            finding_id=finding_id,
            anatomy=kwargs.pop("anatomy", "RUL"),
            diameter_mm=diameter,
            **kwargs,
        )


def _record(scope, memory_id, memory_type, **changes):
    record = {
        "memory_id": memory_id,
        "memory_type": memory_type,
        "doctor_id": scope.doctor_id,
        "patient_id": scope.patient_id,
        "case_id": scope.case_id,
        "thread_id": scope.thread_id,
        "source_type": "case",
        "source_id": scope.case_id,
        "created_at": "2026-09-01T00:00:00+00:00",
        "observed_at": "2026-09-01T00:00:00+00:00",
        "status": "active",
        "confidence": 1.0,
        "text": "Synthetic corrected history",
        "data": {"field": "smoking_history", "value": "never"},
        "logical_key": memory_id,
        "supersedes": None,
    }
    record.update(changes)
    return record


def test_scope_coordinates_come_from_business_thread(entity_db, scope):
    assert scope == MemoryScope("D001", "P001", "C002", scope.thread_id)
    with pytest.raises(AccessDeniedError):
        authorize_scope("D001", scope.thread_id, entity_db, patient_id="P002")
    with pytest.raises(AccessDeniedError):
        authorize_scope("D001", scope.thread_id, entity_db, case_id="C001")
    with pytest.raises(AccessDeniedError):
        authorize_scope("D002", scope.thread_id, entity_db)


def test_forged_and_revoked_scopes_are_rejected_before_retrieval(entity_db, scope):
    temporal = TemporalRetriever(entity_db)
    with pytest.raises(AccessDeniedError):
        temporal.retrieve(replace(scope, patient_id="P002"))
    with pytest.raises(AccessDeniedError):
        temporal.retrieve(replace(scope, patient_id="P002"), observed_after="invalid")
    with transaction(entity_db) as connection:
        connection.execute(
            "DELETE FROM doctor_patient_access WHERE doctor_id = ? AND patient_id = ?",
            (scope.doctor_id, scope.patient_id),
        )
    with pytest.raises(AccessDeniedError):
        revalidate_scope(scope, entity_db)
    with pytest.raises(AccessDeniedError):
        temporal.retrieve(scope)


def test_inactive_doctor_and_read_only_writes_are_rejected(entity_db, scope):
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D001", "P001", access_level="read_only")
    assert revalidate_scope(scope, entity_db) == scope
    with pytest.raises(AccessDeniedError):
        revalidate_scope(scope, entity_db, write=True)
    with transaction(entity_db) as connection:
        UserRepository(connection).deactivate("D001")
    with pytest.raises(EntityNotFoundError):
        TemporalRetriever(entity_db).retrieve(scope)


def test_exact_reopens_preferences_and_records_without_vectors(
    entity_db, scope, tmp_path
):
    path = tmp_path / "exact-memory.sqlite"
    with SqliteStore.from_conn_string(str(path)) as store:
        store.setup()
        service = MemoryService(entity_db, store)
        service.save_doctor_preference("D001", "report_style", {"max_words": 200})
        namespace = ("doctor", "D001", "patient", "P001", "records")
        for record in (
            _record(scope, "corrected", "correction"),
            _record(scope, "old-correction", "correction", status="superseded"),
            _record(scope, "decision", "clinical_decision"),
            _record(scope, "other-doctor", "correction", doctor_id="D002"),
            _record(scope, "other-patient", "correction", patient_id="P002"),
        ):
            store.put(namespace, record["memory_id"], record)
    with SqliteStore.from_conn_string(str(path)) as store:
        store.setup()
        snapshot = ExactRetriever(MemoryService(entity_db, store)).retrieve(
            scope, "Corrected smoking history"
        )
        assert snapshot.doctor_preferences["report_style"] == {"max_words": 200}
        assert {record["memory_id"] for record in snapshot.typed_records} == {
            "corrected",
            "preference:report_style",
        }
        assert snapshot.current_findings[0]["finding_id"] == "F002"
        assert snapshot.historical_observations[0]["finding_id"] == "F001"
    with transaction(entity_db) as connection:
        second = ThreadRepository(connection).create("D001", "C001")
    with SqliteStore.from_conn_string(str(path)) as store:
        store.setup()
        cross_thread = authorize_scope("D001", second, entity_db)
        snapshot = ExactRetriever(MemoryService(entity_db, store)).retrieve(
            cross_thread
        )
        assert snapshot.doctor_preferences["report_style"]["max_words"] == 200


def test_exact_patient_facts_have_sources_and_exclude_name(entity_db, scope, tmp_path):
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE patients SET sex = 'female', birth_date = '1960-01-01' "
            "WHERE id = 'P001'"
        )
        connection.execute(
            "UPDATE cases SET smoking_history = 'never' WHERE id = 'C002'"
        )
    with SqliteStore.from_conn_string(str(tmp_path / "facts-memory.sqlite")) as store:
        store.setup()
        snapshot = ExactRetriever(MemoryService(entity_db, store)).retrieve(scope)
    assert snapshot.patient_facts["sex"] == "female"
    assert snapshot.patient_facts["birth_date"] == "1960-01-01"
    assert snapshot.patient_facts["smoking_history"] == "never"
    assert snapshot.patient_facts["sources"] == [
        {"source_type": "patient", "source_id": "P001"},
        {"source_type": "case", "source_id": "C002"},
    ]
    assert "name" not in snapshot.patient_facts
    assert "clinical_notes_json" not in snapshot.patient_facts


def test_exact_store_failure_keeps_business_facts(entity_db, scope):
    class FailingStore:
        def search(self, *args, **kwargs):
            raise OSError("synthetic unavailable Store")

    snapshot = ExactRetriever(MemoryService(entity_db, FailingStore())).retrieve(scope)
    assert snapshot.available is False
    assert snapshot.error_code == "store_unavailable"
    assert snapshot.current_findings[0]["diameter_mm"] == 8.0
    assert snapshot.patient_facts["case_id"] == "C002"
    assert snapshot.typed_records == []


def test_exact_checks_scope_before_touching_store(entity_db, scope):
    class UntouchedStore:
        def search(self, *args, **kwargs):
            raise AssertionError("Unauthorized exact access must not touch the Store")

    exact = ExactRetriever(MemoryService(entity_db, UntouchedStore()))
    with pytest.raises(AccessDeniedError):
        exact.retrieve(replace(scope, case_id="C003"))


def test_typed_record_failure_keeps_current_sql_facts(
    entity_db, scope, tmp_path, monkeypatch
):
    def failed_records(*args, **kwargs):
        raise OSError("synthetic typed Store failure")

    with SqliteStore.from_conn_string(str(tmp_path / "typed-failure.sqlite")) as store:
        store.setup()
        service = MemoryService(entity_db, store)
        monkeypatch.setattr(service, "list_records", failed_records)
        result = ExactRetriever(service).retrieve(scope)
    assert result.available is False
    assert result.current_findings[0]["diameter_mm"] == 8.0
    assert result.patient_facts["patient_id"] == "P001"
    assert result.typed_records == []


def test_temporal_current_history_and_single_candidate_delta(entity_db, scope):
    result = TemporalRetriever(entity_db).retrieve(scope)
    assert [event["source_finding_id"] for event in result["events"]] == [
        "F001",
        "F002",
    ]
    assert [event["current"] for event in result["events"]] == [False, True]
    assert result["changes"][0]["delta_mm"] == 2.0
    assert result["changes"][0]["match_basis"] == "single_observation_per_time"
    assert "lesion_identity_unconfirmed" in result["warnings"]
    assert all(event["source_type"] == "finding" for event in result["events"])
    assert all(event["doctor_id"] == scope.doctor_id for event in result["events"])
    assert all(event["thread_id"] == scope.thread_id for event in result["events"])
    assert all(event["confidence"] == 1.0 for event in result["events"])
    assert all(event["created_at"] for event in result["events"])


def test_old_case_does_not_recall_future_observations_as_history(entity_db):
    with transaction(entity_db) as connection:
        thread_id = ThreadRepository(connection).create("D001", "C001")
    old = authorize_scope("D001", thread_id, entity_db)
    temporal = TemporalRetriever(entity_db)
    result = temporal.retrieve(old)
    assert [event["finding_id"] for event in result["events"]] == ["F001"]
    assert result["events"][0]["current"] is True
    assert result["changes"] == []
    assert temporal.retrieve(old, source_finding_id="F002")["events"] == []
    assert temporal.retrieve(old, observed_after="2026-09-01")["events"] == []


def test_missing_current_observation_returns_events_without_comparison(
    entity_db, scope
):
    with transaction(entity_db) as connection:
        connection.execute("UPDATE findings SET status = 'draft' WHERE id = 'F002'")
    result = TemporalRetriever(entity_db).retrieve(scope)
    assert [event["finding_id"] for event in result["events"]] == ["F001"]
    assert result["changes"] == []
    assert result["events"][0]["current"] is False
    assert "current_observation_unavailable" in result["warnings"]


def test_temporal_utc_sort_ranges_and_source_filters(entity_db, scope):
    _finding(entity_db, "F-offset", "C001", "2026-06-01T01:00:00+08:00", 5.0)
    temporal = TemporalRetriever(entity_db)
    events = temporal.retrieve(scope)["events"]
    assert [event["finding_id"] for event in events] == ["F-offset", "F001", "F002"]
    assert events[0]["observed_at"] == "2026-05-31T17:00:00+00:00"
    result = temporal.retrieve(
        scope,
        finding_type="nodule",
        body_location="RUL",
        observed_after="2026-06-01",
        observed_before="2026-06-01T00:00:00Z",
    )
    assert [event["finding_id"] for event in result["events"]] == ["F001"]
    assert temporal.retrieve(scope, body_location="LUL")["events"] == []
    assert temporal.retrieve(scope, source_finding_id="F002")["events"][0]["current"]
    assert temporal.retrieve(scope, source_finding_id="missing")["events"] == []
    with pytest.raises(ValueError):
        temporal.retrieve(
            scope, observed_after="2026-09-02", observed_before="2026-09-01"
        )


def test_temporal_filters_superseded_draft_and_other_patient(entity_db, scope):
    _finding(entity_db, "F-old", "C001", "2026-07-01", 7.0, status="superseded")
    _finding(entity_db, "F-draft", "C002", "2026-10-01", 10.0, status="draft")
    _finding(entity_db, "F-other", "C003", "2026-08-01", 12.0)
    result = TemporalRetriever(entity_db).retrieve(scope)
    assert [event["finding_id"] for event in result["events"]] == ["F001", "F002"]
    other = TemporalRetriever(entity_db).retrieve(scope, source_finding_id="F-other")
    assert other["events"] == []


def test_temporal_does_not_match_multiple_lesions_by_anatomy_or_index(entity_db, scope):
    _finding(
        entity_db,
        "F-third",
        "C002",
        "2026-09-01T00:00:00+00:00",
        3.0,
        payload_json=json.dumps({"index": 2}),
    )
    result = TemporalRetriever(entity_db).retrieve(scope)
    assert len(result["events"]) == 3
    assert result["changes"] == []
    assert "ambiguous_observations" in result["warnings"]


def test_temporal_explicit_lesion_identity_builds_multiple_followups(entity_db, scope):
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE findings SET payload_json = ? WHERE id IN ('F001', 'F002')",
            (json.dumps({"lesion_id": "L1"}),),
        )
    _finding(
        entity_db,
        "F-later",
        "C002",
        "2026-10-01",
        9.0,
        payload_json=json.dumps({"lesion_id": "L1"}),
    )
    _finding(
        entity_db,
        "F-second-lesion",
        "C002",
        "2026-09-01",
        3.0,
        payload_json=json.dumps({"lesion_id": "L2"}),
    )
    result = TemporalRetriever(entity_db).retrieve(scope, lesion_id="L1")
    assert [event["diameter_mm"] for event in result["events"]] == [6.0, 8.0, 9.0]
    assert [change["delta_mm"] for change in result["changes"]] == [2.0, 1.0]
    assert all(change["match_basis"] == "lesion_id" for change in result["changes"])
    assert result["warnings"] == []


def test_invalid_time_and_missing_measurement_do_not_fabricate_changes(
    entity_db, scope
):
    _finding(entity_db, "F-invalid", "C002", "not-a-date", 12.0)
    with transaction(entity_db) as connection:
        connection.execute("UPDATE findings SET diameter_mm = NULL WHERE id = 'F001'")
    result = TemporalRetriever(entity_db).retrieve(scope)
    assert [event["finding_id"] for event in result["events"]] == ["F001", "F002"]
    assert result["changes"] == []
    assert "invalid_observed_at" in result["warnings"]
    assert "measurement_unavailable" in result["warnings"]
