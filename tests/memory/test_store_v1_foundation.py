"""Real SqliteStore persistence and business authorization for Memory V1."""

import pytest
from langgraph.store.sqlite import SqliteStore

from martin.db import transaction
from martin.memory.namespaces import (
    case_memory_ns,
    doctor_patient_private_ns,
    doctor_preferences_ns,
    patient_memory_ns,
)
from martin.memory.service import MemoryService
from martin.memory.store import close_default_store, get_default_store
from martin.repositories.access import AccessRepository
from martin.services.access_service import AccessDeniedError


def _open_store(path):
    context = SqliteStore.from_conn_string(str(path))
    store = context.__enter__()
    store.setup()
    return context, store


def test_namespaces_use_distinct_stable_entity_ids():
    assert doctor_preferences_ns("D001") == ("doctor", "D001", "preferences")
    assert doctor_patient_private_ns("D001", "P001") == (
        "doctor", "D001", "patient", "P001", "private"
    )
    assert patient_memory_ns("P001") == ("patient", "P001", "memory")
    assert case_memory_ns("C001") == ("case", "C001", "memory")
    with pytest.raises(ValueError):
        patient_memory_ns("")


def test_doctor_preference_survives_reopen_and_is_isolated(entity_db, tmp_path):
    path = tmp_path / "memory.sqlite"
    context, store = _open_store(path)
    try:
        service = MemoryService(entity_db, store)
        service.save_doctor_preference(
            "D001", "report_style", {"conclusion_first": True, "max_words": 200}
        )
    finally:
        context.__exit__(None, None, None)

    context, store = _open_store(path)
    try:
        service = MemoryService(entity_db, store)
        assert service.get_doctor_preferences("D001")["report_style"][
            "conclusion_first"
        ] is True
        assert service.get_doctor_preferences("D002") == {}
    finally:
        context.__exit__(None, None, None)


def test_two_observations_survive_reopen_and_require_patient_access(
    entity_db, tmp_path
):
    path = tmp_path / "memory.sqlite"
    context, store = _open_store(path)
    try:
        service = MemoryService(entity_db, store)
        assert service.sync_finding("D001", "F001") == "observation:F001"
        assert service.sync_finding("D001", "F002") == "observation:F002"
    finally:
        context.__exit__(None, None, None)

    context, store = _open_store(path)
    try:
        service = MemoryService(entity_db, store)
        observations = service.get_patient_observations("D001", "P001")
        assert [(item["finding_id"], item["diameter_mm"]) for item in observations] == [
            ("F001", 6.0),
            ("F002", 8.0),
        ]
        with pytest.raises(AccessDeniedError):
            service.get_patient_observations("D002", "P001")
        with pytest.raises(AccessDeniedError):
            service.sync_finding("D002", "F001")
    finally:
        context.__exit__(None, None, None)


def test_private_and_case_memory_check_business_access(entity_db, tmp_path):
    context, store = _open_store(tmp_path / "memory.sqlite")
    try:
        service = MemoryService(entity_db, store)
        service.save_private_patient_note(
            "D001", "P001", "next_visit", {"focus": "spiculation"}
        )
        service.save_case_memory("D001", "C001", "follow_up", {"months": 3})
        assert service.get_private_patient_notes("D001", "P001")["next_visit"] == {
            "focus": "spiculation"
        }
        assert service.get_case_memories("D001", "C001")["follow_up"] == {
            "months": 3
        }
        with pytest.raises(AccessDeniedError):
            service.get_private_patient_notes("D002", "P001")
        with pytest.raises(AccessDeniedError):
            service.get_case_memories("D002", "C001")
        assert store.search(doctor_patient_private_ns("D002", "P001")) == []
        with transaction(entity_db) as connection:
            AccessRepository(connection).grant("D002", "P001", access_level="read_only")
        assert service.get_private_patient_notes("D002", "P001") == {}
        with pytest.raises(AccessDeniedError):
            service.save_private_patient_note("D002", "P001", "x", {"text": "x"})
    finally:
        context.__exit__(None, None, None)


def test_default_store_uses_separate_memory_database(tmp_path, monkeypatch):
    path = tmp_path / "memory.sqlite"
    monkeypatch.setenv("MARTIN_MEMORY_DB_PATH", str(path))
    close_default_store()
    try:
        store = get_default_store()
        store.put(doctor_preferences_ns("D001"), "report_style", {"max_words": 200})
        assert path.exists()
        assert get_default_store() is store
    finally:
        close_default_store()
    assert get_default_store().get(doctor_preferences_ns("D001"), "report_style")
    close_default_store()
