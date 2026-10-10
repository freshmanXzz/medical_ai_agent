"""V2.1 A-L contracts using real isolated SQLite and authenticated APIs.

The scripted model tests prompt plumbing only. Live answer semantics are checked
by validation_scripts/memory_governance_live_acceptance.py.
"""

import json
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import PrivateAttr

from martin.db import transaction
from martin.memory.models import MemoryCandidate, new_record
from martin.memory.namespaces import (
    case_memory_ns,
    doctor_patient_private_ns,
    doctor_preferences_ns,
    records_ns,
)
from martin.memory.output_preferences import OutputPreferences
from martin.memory.router import MemoryRetrievalRouter
from martin.memory.scope import authorize_scope
from martin.memory.semantic import SemanticRetriever
from martin.memory.service import MemoryService
from martin.memory.store import close_default_store
from martin.memory.vector_index import MemoryVectorIndex
from martin.memory.writer import MemoryWriter
from martin.repositories.access import AccessRepository
from martin.services.access_service import AccessDeniedError
from martin.services.thread_service import ThreadService


def _scope(db, case="C002", doctor="D001"):
    return authorize_scope(doctor, ThreadService(db).create_thread(doctor, case), db)


def _provenance(scope, submission="synthetic-submission"):
    return {
        "kind": "api_submission",
        "actor_id": scope.doctor_id,
        "actor_role": "doctor",
        "submission_id": submission,
        "thread_id": scope.thread_id,
        "message_id": None,
    }


def _save(
    service, scope, kind="task_followup", text="等待资料复核", key="task", **data
):
    return (
        MemoryWriter(service)
        .write(
            scope,
            [MemoryCandidate(kind, text, key, data=data)],
            source_type="thread",
            source_id=scope.thread_id,
            provenance=_provenance(scope),
        )
        .records[0]
    )


def _login(client, doctor="a"):
    assert (
        client.post(
            "/api/auth/login",
            json={
                "username": f"doctor_{doctor}",
                "password": f"TestDoctor{doctor.upper()}!2026",
            },
        ).status_code
        == 200
    )


def _url(scope, memory_id=None):
    base = f"/api/memory/threads/{scope.thread_id}/records"
    return base if memory_id is None else f"{base}/{memory_id}"


class SyntheticEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class PromptCaptureModel(BaseChatModel):
    _prompts: list[str] = PrivateAttr(default_factory=list)
    _tool_names: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self):
        return "governance-prompt-contract-only"

    def bind_tools(self, tools, **kwargs):
        self._tool_names.update(tool.name for tool in tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._prompts.append(
            "\n".join(str(m.content) for m in messages if isinstance(m, SystemMessage))
        )
        human_index = max(
            i for i, m in enumerate(messages) if isinstance(m, HumanMessage)
        )
        if "请保存长期报告偏好" in messages[human_index].content and not any(
            isinstance(m, ToolMessage) for m in messages[human_index + 1 :]
        ):
            answer = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "save_report_preference",
                        "id": "synthetic-save-preference",
                        "args": {
                            "conclusion_first": True,
                            "max_words": 200,
                            "focus": [],
                        },
                    }
                ],
            )
        else:
            answer = AIMessage(content="结论：当前确认观察值为8mm。")
        return ChatResult(generations=[ChatGeneration(message=answer)])


def _agent_runtime(monkeypatch, saver, model, tmp_path):
    from martin.agent.audit import AuditLogger

    monkeypatch.setattr("martin.agent.agent.get_chat_model", lambda: model)
    monkeypatch.setattr(
        "martin.agent.agent._get_thinking_logger",
        lambda: logging.getLogger("v21-contract"),
    )
    monkeypatch.setattr("martin.agent.sessions.get_default_checkpointer", lambda: saver)
    original = AuditLogger.__init__
    monkeypatch.setattr(
        AuditLogger,
        "__init__",
        lambda self, session_id=None, audit_dir=None: original(
            self, session_id, str(tmp_path / "audit")
        ),
    )


def test_a_message_provenance_tracks_literal_human_not_assistant(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    writer = MemoryWriter(service)
    result = writer.write_interaction(
        scope,
        "请记住：等待资料复核。",
        [MemoryCandidate("task_followup", "等待资料复核")],
        interaction_id="actual-synthetic-human-message",
    )
    record = result.records[0]
    assert record["source_message_id"] == "actual-synthetic-human-message"
    assert record["provenance"]["kind"] == "message"
    assert record["provenance"]["thread_id"] == scope.thread_id
    with pytest.raises(ValueError, match="human fragment"):
        writer.write_interaction(
            scope,
            "本次仅复核",
            [MemoryCandidate("clinical_claim", "模型推断过敏")],
            interaction_id="human-2",
        )
    with pytest.raises(ValueError):
        writer.write(
            scope,
            [MemoryCandidate("clinical_claim", "模型推断过敏")],
            source_type="thread",
            source_id=scope.thread_id,
            provenance=dict(_provenance(scope), actor_role="assistant"),
        )


def test_a_api_submission_has_no_fabricated_message_reference(entity_client, entity_db):
    _login(entity_client)
    scope = _scope(entity_db)
    response = entity_client.post(
        _url(scope),
        json={
            "candidates": [
                {
                    "memory_type": "clinical_claim",
                    "text": "医生陈述曾有药物过敏，尚待核实",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    record = response.json()["records"][0]
    assert record["provenance"]["kind"] == "api_submission"
    assert record["provenance"]["actor_id"] == "D001"
    assert record["provenance"]["submission_id"]
    assert record["source_message_id"] is None
    assert record.get("interaction_id") is None
    assert record["verification_status"] == "unverified"


def test_a_agent_preference_uses_persisted_human_id(
    entity_client, entity_db, tmp_path, monkeypatch
):
    scope = _scope(entity_db)
    model = PromptCaptureModel()
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _agent_runtime(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        response = entity_client.post(
            "/api/agent/chat",
            json={
                "session_id": scope.thread_id,
                "user_message": "请保存长期报告偏好：以后结论前置，200字以内。",
            },
        )
        assert response.status_code == 200, response.text
        checkpoint = saver.get_tuple({"configurable": {"thread_id": scope.thread_id}})
        humans = [
            m
            for m in checkpoint.checkpoint["channel_values"]["messages"]
            if isinstance(m, HumanMessage)
        ]
        record = next(
            r
            for r in MemoryService(entity_db).list_records(scope)
            if r["memory_type"] == "doctor_preference"
        )
        assert record["source_message_id"] in {m.id for m in humans}
        assert record["provenance"]["kind"] == "message"
        assert {
            "inspect_long_term_memory",
            "retract_long_term_memory",
            "save_long_term_memory",
        } <= model._tool_names


def test_bc_preference_revisions_reopen_in_fresh_process(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    first = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_provenance(scope)
    )
    second = service.save_doctor_preference(
        "D001",
        "report_style",
        {"max_words": None, "complex_case_unlimited": True},
        provenance=_provenance(scope, "revision-2"),
        reason="医生更新长期规则",
    )
    assert first["memory_id"] != second["memory_id"]
    assert second["supersedes"] == first["memory_id"]
    history = service.record_history(scope, first["memory_id"])
    assert [item["status"] for item in history] == ["superseded", "active"]
    close_default_store()
    script = """import json
from martin.memory.service import MemoryService
from martin.memory.scope import authorize_scope
s=MemoryService()
scope=authorize_scope('D001', __import__('sys').argv[1], s.db_path)
print(json.dumps({'preferences': s.get_doctor_preferences('D001'),
                  'history': s.record_history(scope, __import__('sys').argv[2])}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, scope.thread_id, first["memory_id"]],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    reopened = json.loads(result.stdout.strip())
    assert reopened["preferences"]["report_style"]["max_words"] is None
    assert [r["memory_id"] for r in reopened["history"]] == [
        first["memory_id"],
        second["memory_id"],
    ]
    assert reopened["history"][0]["audit_events"][-1]["reason"] == "医生更新长期规则"


def test_b_current_task_overrides_and_conditional_rule_does_not_mutate_saved_value():
    policy = OutputPreferences.from_dict(
        {"max_words": 200, "conclusion_first": True, "complex_case_unlimited": True}
    )
    assert policy.for_task("生成报告").max_words == 200
    assert policy.for_task("这是复杂病例，生成报告").max_words is None
    assert policy.for_task("这次不限字数，结论放在最后").max_words is None
    assert policy.for_task("这次不限字数，结论放在最后").conclusion_first is False
    assert policy.for_task("这是复杂病例，请100字以内").max_words == 100
    assert policy.max_words == 200 and policy.conclusion_first


def test_cd_explicit_revision_retraction_idempotency_and_history(
    entity_client, entity_db
):
    _login(entity_client)
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    original = _save(service, scope)
    body = {
        "candidate": {
            "memory_type": "task_followup",
            "text": "已收到资料，等待医生复核",
        },
        "reason": "资料到达",
    }
    revised = entity_client.post(
        _url(scope, original["memory_id"]) + "/revise", json=body
    )
    assert revised.status_code == 200, revised.text
    replacement = revised.json()["records"][0]
    retry = entity_client.post(
        _url(scope, original["memory_id"]) + "/revise", json=body
    )
    assert (
        retry.status_code == 200
        and retry.json()["records"][0]["memory_id"] == replacement["memory_id"]
    )
    history = entity_client.get(
        _url(scope, replacement["memory_id"]) + "/history"
    ).json()["records"]
    assert [r["status"] for r in history] == ["superseded", "active"]
    first = entity_client.post(
        _url(scope, replacement["memory_id"]) + "/retract", json={"reason": "任务取消"}
    )
    again = entity_client.post(
        _url(scope, replacement["memory_id"]) + "/retract", json={"reason": "任务取消"}
    )
    assert first.status_code == again.status_code == 200
    assert (
        first.json()["record"]["audit_events"] == again.json()["record"]["audit_events"]
    )
    assert entity_client.get(_url(scope)).json()["records"] == []
    assert (
        len(
            entity_client.get(_url(scope), params={"include_inactive": True}).json()[
                "records"
            ]
        )
        == 2
    )
    assert entity_client.get(_url(scope, "missing") + "/history").status_code == 404
    assert (
        entity_client.post(
            _url(scope, replacement["memory_id"]) + "/revise", json=body
        ).status_code
        == 400
    )


def test_d_retracted_preference_cannot_revive_through_stale_legacy_projection(
    entity_db,
):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_provenance(scope)
    )
    service.retract_record(
        scope, record["memory_id"], reason="撤回字数限制", provenance=_provenance(scope)
    )
    # Simulate an old projection left behind by a stale client or interrupted upgrade.
    service._store().put(
        doctor_preferences_ns("D001"), "report_style", {"max_words": 200}
    )
    close_default_store()
    second = _scope(entity_db)
    assert service.get_doctor_preferences("D001") == {}
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", second.thread_id, "生成报告"
    )
    assert context.snapshot.doctor_preferences == {}
    assert not any(r["memory_type"] == "doctor_preference" for r in context.records)
    assert (
        service.record_history(second, record["memory_id"])[0]["status"] == "retracted"
    )


def test_d_rest_ws_and_resumed_thread_stop_injecting_retracted_preference(
    entity_client, entity_db, tmp_path, monkeypatch
):
    scope = _scope(entity_db)
    model = PromptCaptureModel()
    service = MemoryService(entity_db)
    record = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_provenance(scope)
    )
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _agent_runtime(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        payload = {"session_id": scope.thread_id, "user_message": "生成报告"}
        assert entity_client.post("/api/agent/chat", json=payload).status_code == 200
        assert '"max_words": 200' in model._prompts[-1]
        assert (
            entity_client.post(
                _url(scope, record["memory_id"]) + "/retract",
                json={"reason": "取消旧偏好"},
            ).status_code
            == 200
        )
        assert entity_client.post("/api/agent/chat", json=payload).status_code == 200
        assert '"max_words": 200' not in model._prompts[-1]
        new_scope = _scope(entity_db)
        with entity_client.websocket_connect(
            f"/api/ws/agent/{new_scope.thread_id}"
        ) as ws:
            assert ws.receive_json()["type"] == "status"
            ws.send_json({"message": "生成报告"})
            for _ in range(12):
                event = ws.receive_json()
                assert event["type"] != "error", event
                if event["type"] == "final":
                    break
            else:
                pytest.fail("No WebSocket final answer")
        assert '"max_words": 200' not in model._prompts[-1]


def test_ef_claim_and_targeted_correction_do_not_change_business_fact(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    with transaction(entity_db) as connection:
        before = [
            tuple(row)
            for row in connection.execute("SELECT * FROM findings ORDER BY id")
        ]
    claim = _save(
        service, scope, "clinical_claim", "医生陈述疑似药物过敏，待核实", "allergy"
    )
    correction = _save(
        service,
        scope,
        "correction",
        "我认为F002直径应为9mm，请复核",
        "diameter",
        target_finding_id="F002",
        field="diameter_mm",
        proposed_value=9,
    )
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", scope.thread_id, "请说明待核实声明与当前数据"
    )
    assert context.conflicts[0]["business_value"] == 8
    assert context.conflicts[0]["proposed_value"] == 9
    assert context.conflicts[0]["status"] == "conflict"
    assert context.conflicts[0]["business_fact_updated"] is False
    assert context.conflicts[0]["source_finding_id"] == "F002"
    for memory_id in (claim["memory_id"], correction["memory_id"]):
        record = next(r for r in context.records if r["memory_id"] == memory_id)
        assert record["authority"] == "unverified_claim"
        assert record["verification_status"] == "unverified"
    assert "尚待核实" in context.to_prompt()
    with transaction(entity_db) as connection:
        assert [
            tuple(row)
            for row in connection.execute("SELECT * FROM findings ORDER BY id")
        ] == before


@pytest.mark.parametrize(
    "data",
    [
        {"field": "diameter_mm", "proposed_value": 9},
        {"target_finding_id": "F002", "field": "status", "proposed_value": "confirmed"},
        {"target_finding_id": "F002", "field": "diameter_mm", "proposed_value": True},
        {"target_finding_id": "F003", "field": "diameter_mm", "proposed_value": 9},
    ],
)
def test_f_invalid_or_foreign_structured_targets_are_rejected(entity_db, data):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    with pytest.raises(ValueError):
        _save(service, scope, "correction", "待核实更正", **data)
    assert service.list_records(scope) == []


def test_f_unstructured_correction_does_not_guess_target(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    _save(service, scope, "correction", "上一条大小可能写错了")
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", scope.thread_id, "更正内容"
    )
    assert context.conflicts == []
    assert context.snapshot.typed_records[0]["verification_status"] == "unverified"


def test_h_stale_semantic_hit_is_rejected_after_retraction(
    entity_db, tmp_path, monkeypatch
):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    index = MemoryVectorIndex(
        tmp_path / "vectors.sqlite", embeddings=SyntheticEmbeddings(), dims=2
    )
    try:
        record = (
            MemoryWriter(service, index)
            .write(
                scope,
                [MemoryCandidate("historical_discussion", "旧讨论：等待复核")],
                source_type="thread",
                source_id=scope.thread_id,
                provenance=_provenance(scope),
            )
            .records[0]
        )
        stale_hits = index.search(scope, "旧讨论")
        assert stale_hits
        service.retract_record(
            scope, record["memory_id"], provenance=_provenance(scope)
        )
        monkeypatch.setattr(index, "sync", lambda *args, **kwargs: None)
        monkeypatch.setattr(index, "search", lambda *args, **kwargs: stale_hits)
        result = SemanticRetriever(service, index).retrieve(scope, "旧讨论")
        assert result["records"] == []
        router = MemoryRetrievalRouter(
            service, semantic=SemanticRetriever(service, index)
        )
        assert (
            "旧讨论：等待复核"
            not in router.retrieve(
                "D001", scope.thread_id, "为什么上次这么讨论"
            ).to_prompt()
        )
    finally:
        index.close()


def test_ij_governance_history_and_mutation_respect_doctor_patient_and_revocation(
    entity_client, entity_db
):
    _login(entity_client)
    service = MemoryService(entity_db)
    own = _scope(entity_db)
    record = _save(service, own)
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D002", "P001")
        AccessRepository(connection).grant("D001", "P002")
    other_doctor = _scope(entity_db, doctor="D002")
    other_patient = _scope(entity_db, case="C003")
    assert service.list_records(other_doctor) == []
    assert service.list_records(other_patient) == []
    assert (
        entity_client.get(
            _url(other_patient, record["memory_id"]) + "/history"
        ).status_code
        == 404
    )
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE doctor_patient_access SET access_level='read_only' WHERE doctor_id='D001' AND patient_id='P001'"
        )
    assert (
        entity_client.get(_url(own, record["memory_id"]) + "/history").status_code
        == 200
    )
    assert (
        entity_client.post(
            _url(own, record["memory_id"]) + "/retract", json={}
        ).status_code
        == 403
    )
    with transaction(entity_db) as connection:
        AccessRepository(connection).revoke("D001", "P001")
    assert (
        entity_client.get(_url(own, record["memory_id"]) + "/history").status_code
        == 403
    )
    with pytest.raises(AccessDeniedError):
        service.record_history(own, record["memory_id"])


def test_k_atomic_preference_failure_keeps_revision_and_projection(
    entity_db, monkeypatch
):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = service.save_doctor_preference(
        "D001", "report_style", {"max_words": 200}, provenance=_provenance(scope)
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            service._store(),
            "batch",
            lambda ops: (_ for _ in ()).throw(OSError("synthetic write fault")),
        )
        with pytest.raises(OSError):
            service.retract_record(
                scope, record["memory_id"], provenance=_provenance(scope)
            )
        with pytest.raises(OSError):
            service.save_doctor_preference(
                "D001",
                "report_style",
                {"max_words": None},
                provenance=_provenance(scope),
            )
    assert service.get_record(scope, record["memory_id"])["status"] == "active"
    assert service.get_doctor_preferences("D001") == {
        "report_style": {"max_words": 200}
    }
    assert len(service.record_history(scope, record["memory_id"])) == 1


def test_k_api_retraction_failure_is_not_acknowledged_as_success(
    entity_client, entity_db, monkeypatch
):
    _login(entity_client)
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = _save(service, scope)
    with monkeypatch.context() as patch:
        patch.setattr(
            service._store(),
            "batch",
            lambda ops: (_ for _ in ()).throw(OSError("synthetic write fault")),
        )
        response = entity_client.post(
            _url(scope, record["memory_id"]) + "/retract", json={}
        )
    assert response.status_code == 503
    assert service.get_record(scope, record["memory_id"])["status"] == "active"


def test_k_store_failure_preserves_current_business_facts(entity_db, monkeypatch):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    monkeypatch.setattr(
        service._store(),
        "search",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic read fault")),
    )
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", scope.thread_id, "和上次相比变化多少"
    )
    assert context.snapshot.current_findings[0]["diameter_mm"] == 8
    assert context.snapshot.available is False
    assert context.snapshot.historical_observations == []
    assert context.temporal["changes"] == []
    assert "不得推断或编造既往测量值" in context.to_prompt()


def test_l_expired_tasks_filtered_but_historical_2024_findings_retained(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE findings SET observed_at='2024-01-01' WHERE id='F001'"
        )
    record = (
        MemoryWriter(service)
        .write(
            scope,
            [
                MemoryCandidate(
                    "task_followup", "仅当天有效的临时任务", valid_until="2024-01-02"
                )
            ],
            source_type="thread",
            source_id=scope.thread_id,
            provenance=_provenance(scope),
        )
        .records[0]
    )
    assert service.get_record(scope, record["memory_id"]) is None
    assert service.get_record(scope, record["memory_id"], include_inactive=True)
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", scope.thread_id, "和上次相比变化多少"
    )
    assert context.snapshot.historical_observations[0]["observed_at"].startswith("2024")
    assert context.temporal["changes"][0]["delta_mm"] == 2
    assert "lesion_identity_unconfirmed" in json.dumps(context.temporal)
    assert "未确认同一病灶" in context.to_prompt()
    assert "仅当天有效的临时任务" not in context.to_prompt()


def test_legacy_unknown_and_inactive_snapshot_sections_are_governed(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    service.save_private_patient_note(
        "D001", "P001", "legacy", {"text": "旧版医生备注"}
    )
    service.save_private_patient_note(
        "D001", "P001", "withdrawn", {"text": "撤回备注不应注入", "status": "retracted"}
    )
    service.save_case_memory(
        "D001", "C002", "invalid", {"text": "失效病例记忆不应注入", "status": "invalid"}
    )
    service.save_case_memory(
        "D001",
        "C002",
        "expired",
        {"text": "过期病例记忆不应注入", "valid_until": "2024-01-01"},
    )
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", scope.thread_id, "当前病例"
    )
    assert (
        context.snapshot.private_notes["legacy"]["provenance"]["kind"]
        == "legacy_unknown"
    )
    assert context.snapshot.private_notes["legacy"]["authority"] == "unverified_context"
    assert set(context.snapshot.private_notes) == {"legacy"}
    assert context.snapshot.case_memories == {}
    assert "不应注入" not in context.to_prompt()


def test_legacy_typed_record_is_read_adapted_without_inventing_message(entity_db):
    scope = _scope(entity_db)
    service = MemoryService(entity_db)
    record = new_record(
        scope,
        MemoryCandidate("task_followup", "旧版待办"),
        source_type="thread",
        source_id=scope.thread_id,
    )
    for field in ("schema_version", "source_message_id", "provenance"):
        record.pop(field, None)
    service._store().put(records_ns("D001", "P001"), record["memory_id"], record)
    read = service.get_record(scope, record["memory_id"])
    assert read["provenance"]["kind"] == "legacy_unknown"
    assert read["source_message_id"] is None
    stored = service._store().get(records_ns("D001", "P001"), record["memory_id"]).value
    assert "provenance" not in stored and "source_message_id" not in stored
