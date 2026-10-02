"""Writer, router and public API contracts against real isolated SQLite."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage

from martin.db import transaction
from martin.memory.interaction import (
    MemoryInteraction, reset_interaction, set_interaction,
)
from martin.memory.models import MemoryCandidate
from martin.memory.models import new_record
from martin.memory.namespaces import records_ns
from martin.memory.output_preferences import (
    OutputPreferences, PreferenceValidationError, enforce_preferences,
)
from martin.memory.router import MemoryRetrievalRouter
from martin.memory.scope import authorize_scope
from martin.memory.semantic import SemanticRetriever
from martin.memory.service import MemoryService
from martin.memory.store import get_default_store
from martin.memory.vector_index import MemoryVectorIndex
from martin.memory.writer import MemoryWriter
from martin.services.access_service import AccessDeniedError
from martin.services.thread_service import ThreadService


class SyntheticEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if "观察" in text else [0.0, 1.0]


def _scope(db, case="C002"):
    thread = ThreadService(db).create_thread("D001", case)
    return authorize_scope("D001", thread, db)


def _login(client, doctor="a"):
    assert client.post("/api/auth/login", json={
        "username": f"doctor_{doctor}",
        "password": f"TestDoctor{doctor.upper()}!2026",
    }).status_code == 200


def test_writer_deduplicates_and_supersedes_across_threads(entity_db):
    first, second = _scope(entity_db), _scope(entity_db)
    service = MemoryService(entity_db)
    writer = MemoryWriter(service)
    old = MemoryCandidate("task_followup", "等待复查结果", "followup")
    saved = writer.write(first, [old], source_type="thread", source_id=first.thread_id)
    repeated = writer.write(second, [old], source_type="thread", source_id=second.thread_id)
    assert repeated.deduplicated == 1
    assert repeated.records[0]["memory_id"] == saved.records[0]["memory_id"]
    new = MemoryCandidate("task_followup", "结果已到，等待医生复核", "followup")
    replaced = writer.write(second, [new], source_type="thread", source_id=second.thread_id)
    active = service.list_records(second)
    assert [item["text"] for item in active] == [new.text]
    assert active[0]["supersedes"] == saved.records[0]["memory_id"]
    all_records = service.list_records(second, include_inactive=True)
    assert len(all_records) == 2
    superseded = next(item for item in all_records if item["status"] == "superseded")
    assert superseded["superseded_by"] == replaced.records[0]["memory_id"]
    assert service.get_record(second, superseded["memory_id"]) is None


def test_correction_is_exact_statement_without_mutating_fact(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    result = MemoryWriter(service).write(
        scope, [MemoryCandidate("correction", "更正：报告标签写右上叶", "label")],
        source_type="thread", source_id=scope.thread_id,
    )
    context = MemoryRetrievalRouter(service).retrieve("D001", scope.thread_id, "召回纠正")
    assert context.plan.semantic is False
    assert result.records[0]["data"]["business_fact_updated"] is False
    assert context.snapshot.typed_records[0]["memory_type"] == "correction"
    with transaction(entity_db) as connection:
        row = connection.execute("SELECT diameter_mm FROM findings WHERE id='F002'").fetchone()
    assert row["diameter_mm"] == 8


@pytest.mark.parametrize("kind", ["patient_fact", "medical_observation", "case_evolution"])
def test_writer_rejects_second_clinical_fact_source(entity_db, kind):
    scope = _scope(entity_db)
    with pytest.raises(ValueError, match="business SQL"):
        MemoryWriter(MemoryService(entity_db)).write(
            scope, [MemoryCandidate(kind, "当前结节99mm")],
            source_type="thread", source_id=scope.thread_id,
        )
    assert MemoryService(entity_db).list_records(scope) == []


def test_interaction_selects_literal_fragment_and_never_model_reasoning(entity_db):
    scope = _scope(entity_db)
    writer = MemoryWriter(MemoryService(entity_db))
    with pytest.raises(ValueError, match="human fragment"):
        writer.write_interaction(
            scope, "这个患者需要讨论", [MemoryCandidate("task_followup", "三个月后复查")],
            interaction_id="synthetic-human-id",
        )
    candidate = MemoryCandidate("correction", "更正报告标签", data={})
    saved = writer.write_interaction(
        scope, "更正报告标签。今天仅复核当前资料。", [candidate],
        interaction_id="synthetic-human-id",
    )
    assert saved.records[0]["text"] == "更正报告标签"
    assert saved.records[0]["interaction_id"] == "synthetic-human-id"
    assert candidate.data == {}
    with pytest.raises(ValueError, match="Reasoning"):
        MemoryCandidate("historical_discussion", "讨论", data={"reasoning": "hidden"}).validate()


def test_semantic_failure_keeps_durable_source_and_exact_temporal(entity_db, tmp_path):
    history, current = _scope(entity_db, "C001"), _scope(entity_db)
    service = MemoryService(entity_db)
    index = MemoryVectorIndex(tmp_path / "vectors.sqlite", embeddings=SyntheticEmbeddings(), dims=2)
    try:
        saved = MemoryWriter(service, index).write(
            history, [MemoryCandidate("clinical_decision", "观察，因为需要复核原始资料")],
            source_type="thread", source_id=history.thread_id,
        )
        assert saved.index_available
        service.save_doctor_preference("D001", "report_style", {"max_words": 200})
        router = MemoryRetrievalRouter(service, semantic=SemanticRetriever(service, index))
        result = router.retrieve("D001", current.thread_id, "为什么上次观察，现在变化多少？")
        assert result.plan.temporal and result.plan.semantic
        assert result.temporal["changes"][0]["delta_mm"] == 2
        evolution = next(
            record for record in result.records
            if record["memory_type"] == "case_evolution"
        )
        assert evolution["doctor_id"] == "D001"
        assert evolution["patient_id"] == current.patient_id
        assert evolution["case_id"] == "C002"
        assert evolution["thread_id"] == current.thread_id
        assert evolution["source_type"] == "finding"
        assert evolution["source_id"] == "F002"
        assert evolution["data"]["previous_finding_id"] == "F001"
        assert evolution["data"]["current_finding_id"] == "F002"
        assert evolution["status"] == "confirmed"
        assert evolution["created_at"] and evolution["observed_at"]
        assert evolution["confidence"] == 1.0
        assert result.semantic["records"][0]["memory_id"] == saved.records[0]["memory_id"]
        assert len({record["memory_id"] for record in result.records}) == len(result.records)
        original = index.search
        index.search = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic index fault"))
        degraded = router.retrieve("D001", current.thread_id, "为什么上次观察，现在变化多少？")
        index.search = original
        assert degraded.retrieval_status["exact"] == "available"
        assert degraded.retrieval_status["temporal"] == "available"
        assert degraded.temporal["changes"][0]["delta_mm"] == 2
        assert degraded.semantic["available"] is False
        assert not any(record.get("retrieval_method") == "semantic" for record in degraded.records)
        assert "语义历史讨论暂不可用" in degraded.to_prompt()
    finally:
        index.close()


def test_writer_index_failure_reports_partial_status_and_source_survives(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    def fail_sync(*args, **kwargs):
        raise OSError("synthetic index write failure")
    writer = MemoryWriter(service, SimpleNamespace(sync=fail_sync))
    result = writer.write(
        scope, [MemoryCandidate("clinical_decision", "选择观察，等待结果")],
        source_type="thread", source_id=scope.thread_id,
    )
    assert result.index_available is False
    assert result.error_code == "semantic_index_unavailable"
    assert service.get_record(scope, result.records[0]["memory_id"])


def test_writer_source_failure_does_not_supersede_previous(entity_db, monkeypatch):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    writer = MemoryWriter(service)
    saved = writer.write(
        scope, [MemoryCandidate("task_followup", "等待结果", "task")],
        source_type="thread", source_id=scope.thread_id,
    )
    with monkeypatch.context() as patch:
        patch.setattr(service._store(), "batch", lambda ops: (_ for _ in ()).throw(OSError("synthetic source failure")))
        with pytest.raises(OSError):
            writer.write(scope, [MemoryCandidate("task_followup", "等待复核", "task")],
                         source_type="thread", source_id=scope.thread_id)
    assert service.list_records(scope)[0]["memory_id"] == saved.records[0]["memory_id"]


def test_old_current_case_does_not_label_newer_case_as_history(entity_db):
    scope = _scope(entity_db, "C001")
    context = MemoryRetrievalRouter(MemoryService(entity_db)).retrieve(
        "D001", scope.thread_id, "和上次相比有变化吗？",
    )
    assert context.snapshot.historical_observations == []
    assert all(event["finding_id"] != "F002" for event in context.temporal["events"])
    assert context.temporal["changes"] == []
    assert context.snapshot.current_findings[0]["diameter_mm"] == 6


def test_api_source_coordinates_and_read_only_permissions(entity_client, entity_db):
    _login(entity_client)
    thread = _scope(entity_db).thread_id
    response = entity_client.post(f"/api/memory/threads/{thread}/records", json={
        "candidates": [{"memory_type": "correction", "text": "更正显示标签", "logical_key": "label"}],
        "doctor_id": "D002", "patient_id": "P002",
    })
    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record["doctor_id"] == "D001" and record["patient_id"] == "P001"
    assert record["data"]["business_fact_updated"] is False
    recalled = entity_client.post(f"/api/memory/threads/{thread}/retrieve", json={"query": "纠正显示标签"})
    assert recalled.status_code == 200
    assert recalled.json()["snapshot"]["typed_records"][0]["memory_id"] == record["memory_id"]
    mismatch = entity_client.post(f"/api/memory/threads/{thread}/retrieve", json={"query": "历史", "patient_id": "P002"})
    assert mismatch.status_code == 403
    with transaction(entity_db) as connection:
        connection.execute("UPDATE doctor_patient_access SET access_level='read_only' WHERE doctor_id='D001' AND patient_id='P001'")
    assert entity_client.get(f"/api/memory/threads/{thread}/records").status_code == 200
    denied = entity_client.post(f"/api/memory/threads/{thread}/records", json={"candidates": [{"memory_type": "task_followup", "text": "等待结果"}]})
    assert denied.status_code == 403
    _login(entity_client, "b")
    assert entity_client.post(f"/api/memory/threads/{thread}/retrieve", json={"query": "历史"}).status_code == 403


def test_report_memory_failure_cannot_retain_optimistic_acknowledgement():
    original = "已保存讨论。结论：当前8mm。长期记忆保存失败，本次内容未确认写入。"
    with pytest.raises(PreferenceValidationError):
        enforce_preferences(original, OutputPreferences(), lambda messages: AIMessage(content=original),
                            memory_persistence_failed=True)
    fixed = "结论：当前8mm。长期记忆保存失败，本次内容未确认写入。"
    answer, evidence = enforce_preferences(
        original, OutputPreferences(), lambda messages: AIMessage(content=fixed),
        memory_persistence_failed=True,
    )
    assert answer == fixed and evidence["rewrite_attempts"] == 1


def test_half_year_query_uses_structured_time_window(entity_db):
    from martin.repositories.findings import FindingRepository

    scope = _scope(entity_db)
    with transaction(entity_db) as connection:
        FindingRepository(connection).create(
            "C001", "nodule", "2025-12-01", anatomy="RUL", diameter_mm=5,
        )
    result = MemoryRetrievalRouter(MemoryService(entity_db)).retrieve(
        "D001", scope.thread_id, "半年内有什么变化？",
    )
    assert [event["finding_id"] for event in result.temporal["events"]] == [
        "F001", "F002",
    ]
    assert result.temporal["changes"][0]["delta_mm"] == 2


def test_bad_record_is_skipped_and_batch_returns_final_revision_status(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    result = MemoryWriter(service).write(
        scope, [MemoryCandidate("task_followup", "等待结果", "task"),
                MemoryCandidate("task_followup", "等待医生复核", "task")],
        source_type="thread", source_id=scope.thread_id,
    )
    assert [record["status"] for record in result.records] == ["superseded", "active"]
    invalid = new_record(
        scope, MemoryCandidate("correction", "标签声明"),
        source_type="thread", source_id=scope.thread_id,
    )
    invalid["observed_at"] = None
    service._store().put(records_ns("D001", "P001"), invalid["memory_id"], invalid)
    another = dict(invalid, memory_id="bad-type", memory_type=[])
    service._store().put(records_ns("D001", "P001"), "bad-type", another)
    assert service.get_record(scope, invalid["memory_id"]) is None
    assert len(service.list_records(scope)) == 1


@pytest.mark.parametrize("data", [
    {"meta": {"reasoning": "private"}}, {"value": float("nan")},
    {"value": float("inf")},
])
def test_writer_rejects_nested_reasoning_and_nonfinite_values(data):
    with pytest.raises(ValueError):
        MemoryCandidate("historical_discussion", "选择的片段", data=data).validate()
