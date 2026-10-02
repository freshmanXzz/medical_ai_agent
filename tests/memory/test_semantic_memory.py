"""Real native vector persistence, scope enforcement, and source revalidation."""

from dataclasses import replace

import pytest
from langchain_core.embeddings import Embeddings
from langgraph.store.sqlite import SqliteStore

from martin.db import transaction
from martin.memory.models import MemoryCandidate, new_record
from martin.memory.namespaces import doctor_records_ns, records_ns
from martin.memory.scope import authorize_scope
from martin.memory.semantic import SemanticRetriever
from martin.memory.service import MemoryService
from martin.memory.vector_index import (
    MemoryVectorIndex,
    close_default_vector_index,
    get_default_vector_index,
)
from martin.repositories.access import AccessRepository
from martin.repositories.threads import ThreadRepository
from martin.services.access_service import AccessDeniedError


class SyntheticEmbedding(Embeddings):
    """Known cosine geometry; no model or network replaces native SQLite."""

    def embed_documents(self, texts):
        vectors = []
        for text in texts:
            if "观察" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "类似" in text or "讨论" in text:
                vectors.append([0.8, 0.6, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors

    def embed_query(self, text):
        return self.embed_documents([text])[0]


@pytest.fixture
def semantic_runtime(entity_db, tmp_path):
    with transaction(entity_db) as connection:
        threads = ThreadRepository(connection)
        previous = threads.create("D001", "C001")
        current = threads.create("D001", "C002")
    with SqliteStore.from_conn_string(str(tmp_path / "source_memory.sqlite")) as store:
        store.setup()
        index = MemoryVectorIndex(
            tmp_path / "memory_vectors.sqlite", embeddings=SyntheticEmbedding(), dims=3
        )
        service = MemoryService(entity_db, store)
        try:
            yield (
                service,
                index,
                authorize_scope("D001", previous, entity_db),
                authorize_scope("D001", current, entity_db),
            )
        finally:
            index.close()


def _record(service, scope, key, text="此前选择继续观察，等待复查。", *,
            memory_type="clinical_decision", observed_at="2026-06-01T00:00:00Z"):
    record = new_record(
        scope, MemoryCandidate(memory_type, text=text, observed_at=observed_at),
        source_type="thread", source_id=scope.thread_id,
    )
    record["memory_id"] = key
    service.store.put(records_ns(scope.doctor_id, scope.patient_id), key, record)
    return record


def test_native_cosine_persistence_and_related_ranking(semantic_runtime):
    service, index, old, current = semantic_runtime
    _record(service, old, "decision")
    _record(service, old, "discussion", "以前讨论过类似的小结节。",
            memory_type="historical_discussion")
    _record(service, old, "unrelated", "办公室打印机需要更换墨盒。")
    result = SemanticRetriever(service, index).retrieve(current, "之前为什么选择观察？")
    assert result["available"] is True
    assert [item["memory_id"] for item in result["records"]] == [
        "decision", "discussion"
    ]
    assert result["records"][0]["score"] == pytest.approx(1.0)
    assert result["records"][0]["source_id"] == old.thread_id
    index.close()
    reopened = MemoryVectorIndex(index.db_path, embeddings=SyntheticEmbedding(), dims=3)
    try:
        assert reopened.search(current, "观察")[0]["memory_id"] == "decision"
    finally:
        reopened.close()


def test_case_time_and_type_filters_before_top_k(semantic_runtime):
    service, index, old, current = semantic_runtime
    _record(service, old, "old_high_score")
    _record(service, current, "current_discussion", "此前讨论过类似情况。",
            memory_type="historical_discussion", observed_at="2026-09-01T00:00:00Z")
    _record(service, current, "late_high_score", observed_at="2026-10-01T00:00:00Z")
    index.sync(current, service.list_records(current))
    candidates = index.search(
        current, "观察", limit=1, case_id="C002",
        observed_after="2026-08-01T00:00:00+00:00",
        observed_before="2026-09-30T00:00:00+00:00",
        memory_types=["historical_discussion"],
    )
    assert [item["memory_id"] for item in candidates] == ["current_discussion"]
    result = SemanticRetriever(service, index).retrieve(
        current, "观察", limit=1, case_id="C002",
        observed_after="2026-08-01T08:00:00+08:00",
        observed_before="2026-09-30T00:00:00Z",
        memory_types=["historical_discussion"],
    )
    assert [item["memory_id"] for item in result["records"]] == ["current_discussion"]


def test_private_doctor_and_patient_scopes_are_isolated(semantic_runtime):
    service, index, old, current = semantic_runtime
    _record(service, old, "own")
    with transaction(service.db_path) as connection:
        access = AccessRepository(connection)
        access.grant("D002", "P001")
        access.grant("D001", "P002")
        threads = ThreadRepository(connection)
        other_doctor_thread = threads.create("D002", "C002")
        other_patient_thread = threads.create("D001", "C003")
    other_doctor = authorize_scope("D002", other_doctor_thread, service.db_path)
    other_patient = authorize_scope("D001", other_patient_thread, service.db_path)
    _record(service, other_doctor, "other_doctor")
    _record(service, other_patient, "other_patient")
    index.sync(other_doctor, service.list_records(other_doctor))
    index.sync(other_patient, service.list_records(other_patient))
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert [item["memory_id"] for item in result["records"]] == ["own"]


def test_revoked_and_forged_scope_never_searches_index(semantic_runtime, monkeypatch):
    service, index, old, current = semantic_runtime
    _record(service, old, "own")
    called = []
    monkeypatch.setattr(index, "search", lambda *args, **kwargs: called.append(True))
    retriever = SemanticRetriever(service, index)
    with pytest.raises(AccessDeniedError):
        retriever.retrieve(replace(current, patient_id="P002"), "观察")
    with transaction(service.db_path) as connection:
        AccessRepository(connection).revoke("D001", "P001")
    with pytest.raises(AccessDeniedError):
        retriever.retrieve(current, "观察")
    assert called == []


def test_superseded_deleted_and_orphaned_sources_are_excluded(semantic_runtime):
    service, index, old, current = semantic_runtime
    original = _record(service, old, "superseded")
    deleted = _record(service, current, "deleted")
    orphan = _record(service, old, "orphan")
    _record(service, current, "valid", "讨论过类似变化。",
            memory_type="historical_discussion")
    index.sync(current, service.list_records(current))
    namespace = records_ns(current.doctor_id, current.patient_id)
    service.store.put(
        namespace, original["memory_id"], dict(original, status="superseded")
    )
    service.store.delete(namespace, deleted["memory_id"])
    service.store.put(namespace, orphan["memory_id"], dict(orphan, source_id="missing"))
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert [item["memory_id"] for item in result["records"]] == ["valid"]
    assert [item["memory_id"] for item in index.search(current, "观察")] == ["valid"]


def test_source_deleted_after_vector_search_is_rechecked(semantic_runtime, monkeypatch):
    service, index, old, current = semantic_runtime
    _record(service, old, "deleted_during_search")
    search = index.search

    def delete_during_search(*args, **kwargs):
        hits = search(*args, **kwargs)
        service.store.delete(
            records_ns(current.doctor_id, current.patient_id), "deleted_during_search"
        )
        return hits

    monkeypatch.setattr(index, "search", delete_during_search)
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert result == {"records": [], "available": True, "error_code": None}


def test_exact_and_global_workflow_records_do_not_enter_patient_index(semantic_runtime):
    service, index, old, current = semantic_runtime
    _record(service, old, "decision")
    _record(service, old, "correction", memory_type="correction")
    workflow = _record(
        service, old, "global_workflow", memory_type="workflow_preference"
    )
    service.store.delete(records_ns(old.doctor_id, old.patient_id), "global_workflow")
    workflow.update(patient_id=None, case_id=None, thread_id=None,
                    source_type="doctor", source_id=old.doctor_id)
    service.store.put(doctor_records_ns(old.doctor_id), "global_workflow", workflow)
    index.sync(current, service.list_records(current))
    assert [item["memory_id"] for item in index.search(current, "观察")] == ["decision"]


@pytest.mark.parametrize("operation", ["sync", "search"])
def test_index_fault_degrades_without_losing_source(
    semantic_runtime, monkeypatch, operation
):
    service, index, old, current = semantic_runtime
    _record(service, old, "durable")

    def fail(*args, **kwargs):
        raise OSError("synthetic vector failure")

    monkeypatch.setattr(index, operation, fail)
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert result == {
        "records": [], "available": False, "error_code": "semantic_index_unavailable"
    }
    assert service.get_record(current, "durable")["status"] == "active"


def test_source_store_failure_is_reported(semantic_runtime, monkeypatch):
    service, index, old, current = semantic_runtime

    def fail(*args, **kwargs):
        raise OSError("synthetic source failure")

    monkeypatch.setattr(service, "list_records", fail)
    assert SemanticRetriever(service, index).retrieve(current, "观察") == {
        "records": [], "available": False, "error_code": "memory_store_unavailable"
    }


def test_default_index_opening_failure_degrades(semantic_runtime, monkeypatch):
    service, index, old, current = semantic_runtime
    _record(service, old, "durable")

    def fail():
        raise OSError("synthetic factory failure")

    monkeypatch.setattr("martin.memory.semantic.get_default_vector_index", fail)
    result = SemanticRetriever(service).retrieve(current, "观察")
    assert result == {
        "records": [], "available": False, "error_code": "semantic_index_unavailable"
    }
    assert service.get_record(current, "durable")


def test_default_vector_cache_tracks_its_own_path(tmp_path, monkeypatch):
    close_default_vector_index()
    monkeypatch.setenv("MARTIN_MEMORY_VECTOR_DB_PATH", str(tmp_path / "first.sqlite"))
    first = get_default_vector_index()
    assert get_default_vector_index() is first
    monkeypatch.setenv("MARTIN_MEMORY_VECTOR_DB_PATH", str(tmp_path / "second.sqlite"))
    try:
        assert get_default_vector_index() is not first
        assert get_default_vector_index().db_path == tmp_path / "second.sqlite"
    finally:
        close_default_vector_index()


def test_database_path_collisions_fail_before_writing(semantic_runtime, monkeypatch):
    service, index, old, current = semantic_runtime
    records = [_record(service, old, "durable")]
    source_path = service.store.conn.execute("PRAGMA database_list").fetchone()[2]
    for path in (service.db_path, source_path):
        collision = MemoryVectorIndex(path, embeddings=SyntheticEmbedding(), dims=3)
        with pytest.raises(ValueError, match="independent file"):
            collision.sync(current, records, reserved_paths=[path])
    assert service.get_record(current, "durable")


def test_missing_derived_vector_is_rebuilt_from_source(semantic_runtime):
    service, index, old, current = semantic_runtime
    _record(service, old, "surviving_source")
    index.sync(current, service.list_records(current))
    with index._store.conn:
        index._store.conn.execute("DELETE FROM store_vectors")
    assert index.search(current, "观察") == []
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert [record["memory_id"] for record in result["records"]] == [
        "surviving_source"
    ]


def test_deleted_business_thread_cannot_remain_semantic_evidence(semantic_runtime):
    service, index, old, current = semantic_runtime
    _record(service, old, "orphaned_thread")
    _record(service, current, "current_valid")
    index.sync(current, service.list_records(current))
    with transaction(service.db_path) as connection:
        ThreadRepository(connection).delete(old.thread_id)
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert [record["memory_id"] for record in result["records"]] == ["current_valid"]


def test_access_revoked_during_vector_search_is_rechecked(
    semantic_runtime, monkeypatch
):
    service, index, old, current = semantic_runtime
    _record(service, old, "own")
    search = index.search

    def revoke_during_search(*args, **kwargs):
        hits = search(*args, **kwargs)
        with transaction(service.db_path) as connection:
            AccessRepository(connection).revoke("D001", "P001")
        return hits

    monkeypatch.setattr(index, "search", revoke_during_search)
    with pytest.raises(AccessDeniedError):
        SemanticRetriever(service, index).retrieve(current, "观察")


def test_knowledge_and_memory_native_stores_never_mix(semantic_runtime, tmp_path):
    from chromadb.config import Settings
    from langchain_chroma import Chroma

    service, index, old, current = semantic_runtime
    knowledge = Chroma(
        collection_name="synthetic_knowledge",
        persist_directory=str(tmp_path / "knowledge"),
        embedding_function=SyntheticEmbedding(),
        client_settings=Settings(anonymized_telemetry=False),
    )
    knowledge.add_texts(["合成知识资料：观察与复查。"], ids=["guideline"])
    _record(service, old, "private_memory")
    result = SemanticRetriever(service, index).retrieve(current, "观察")
    assert [record["memory_id"] for record in result["records"]] == ["private_memory"]
    documents = knowledge.similarity_search("观察", k=5)
    assert [document.page_content for document in documents] == ["合成知识资料：观察与复查。"]
