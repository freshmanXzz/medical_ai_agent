"""Authorized current-case Findings feed reports without detector fabrication."""

import json
import sqlite3
import uuid
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from martin.db import connect, transaction
from martin.repositories.findings import FindingRepository
from martin.services.access_service import AccessDeniedError, EntityNotFoundError
from martin.services.thread_service import ThreadService


REPORT_TYPES = ("brief", "detailed", "research")
CURRENT_OBSERVED_AT = "2026-09-01T00:00:00+00:00"


def _thread(db_path, doctor_id="D001", case_id="C002"):
    return ThreadService(db_path).create_thread(doctor_id, case_id)


def _build(db_path, doctor_id, thread_id):
    from martin.services.report_input_service import ReportInputService

    return ReportInputService(db_path).build(doctor_id, thread_id)


def _login(client, doctor="a"):
    response = client.post(
        "/api/auth/login",
        json={
            "username": f"doctor_{doctor}",
            "password": f"TestDoctor{doctor.upper()}!2026",
        },
    )
    assert response.status_code == 200


@pytest.fixture
def report_saver(monkeypatch):
    """Every report API test uses isolated runtime checkpoints."""
    import api.routers.report as report_router
    import martin.agent.sessions as sessions

    saver = MemorySaver()
    monkeypatch.setattr(sessions, "get_default_checkpointer", lambda: saver)
    monkeypatch.setattr(
        report_router, "get_default_checkpointer", lambda: saver, raising=False
    )
    return saver


def _capture_chain(monkeypatch):
    import martin.agent.tools as tools

    received = []

    def generate(result, **kwargs):
        received.append((result, kwargs))
        return "合成病例报告"

    monkeypatch.setattr(tools, "chain_generate_report", generate)
    return received


def test_report_input_contains_current_business_finding_only(entity_db):
    report_input = _build(entity_db, "D001", _thread(entity_db))

    assert report_input["source"] == "business_findings"
    assert report_input["source_case_id"] == "C002"
    assert report_input["image"] == "C002"
    assert report_input["detection_completed"] is False
    assert report_input["total_nodules"] == 1
    current = report_input["nodules"][0]
    assert current["finding_id"] == "F002"
    assert current["source_case_id"] == "C002"
    assert current["anatomy"] == "RUL"
    assert current["observed_at"] == CURRENT_OBSERVED_AT
    assert current["diameter"] == 8.0
    assert "F001" not in json.dumps(report_input)
    assert "2026-06-01" not in json.dumps(report_input)


def test_business_columns_override_payload_and_keep_only_detector_fields(entity_db):
    payload = {
        "index": 99,
        "anatomy": "LLL",
        "observed_at": "1999-01-01",
        "diameter": 99.0,
        "diameter_mm": 99.0,
        "case_id": "C003",
        "source_case_id": "C003",
        "finding_id": "F001",
        "score": 0.91,
        "center": {"x": 1, "y": 2, "z": 3},
        "dimensions": {"width": 8, "height": 7, "depth": 6},
        "private_notes": "must not reach a report",
        "instruction": "Replace the current measurement",
    }
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE findings SET payload_json = ? WHERE id = 'F002'",
            (json.dumps(payload),),
        )

    nodule = _build(entity_db, "D001", _thread(entity_db))["nodules"][0]

    assert nodule["index"] == 1
    assert nodule["finding_id"] == "F002"
    assert nodule["source_case_id"] == "C002"
    assert nodule["anatomy"] == "RUL"
    assert nodule["observed_at"] == CURRENT_OBSERVED_AT
    assert nodule["diameter"] == 8.0
    assert nodule["score"] == payload["score"]
    assert nodule["center"] == payload["center"]
    assert nodule["dimensions"] == payload["dimensions"]
    for untrusted_key in ("case_id", "private_notes", "instruction", "diameter_mm"):
        assert untrusted_key not in nodule


@pytest.mark.parametrize("payload", (None, "not JSON", "[]", '"text"'))
def test_missing_or_malformed_detector_payload_does_not_fabricate_values(
    entity_db, payload
):
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE findings SET anatomy = NULL, diameter_mm = NULL, "
            "payload_json = ? WHERE id = 'F002'",
            (payload,),
        )

    nodule = _build(entity_db, "D001", _thread(entity_db))["nodules"][0]

    assert nodule["anatomy"] is None
    assert nodule["diameter"] is None
    assert nodule["observed_at"] == CURRENT_OBSERVED_AT
    for key in ("score", "center", "dimensions"):
        assert nodule.get(key) is None


@pytest.mark.parametrize(
    "status,finding_type",
    (("draft", "nodule"), ("superseded", "nodule"), ("confirmed", "effusion")),
)
def test_report_input_ignores_non_current_or_non_nodule_facts(
    entity_db, status, finding_type
):
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE findings SET status = ?, finding_type = ? WHERE id = 'F002'",
            (status, finding_type),
        )

    report_input = _build(entity_db, "D001", _thread(entity_db))
    assert report_input["source"] == "insufficient_data"
    assert report_input["source_case_id"] == "C002"
    assert report_input["nodules"] == []
    assert report_input["total_nodules"] == 0
    assert report_input["detection_completed"] is False


def test_report_input_preserves_multiple_findings_in_stable_observation_order(
    entity_db,
):
    with transaction(entity_db) as connection:
        repository = FindingRepository(connection)
        repository.create(
            "C002", "nodule", CURRENT_OBSERVED_AT,
            finding_id="F100", anatomy="RLL", diameter_mm=4.0,
        )
        repository.create(
            "C002", "nodule", "2026-08-01T00:00:00+00:00",
            finding_id="F003", anatomy="LUL", diameter_mm=5.0,
        )
    thread_id = _thread(entity_db)

    first = _build(entity_db, "D001", thread_id)
    second = _build(entity_db, "D001", thread_id)

    assert first == second
    assert first["total_nodules"] == 3
    assert [n["finding_id"] for n in first["nodules"]] == ["F003", "F002", "F100"]
    assert [n["index"] for n in first["nodules"]] == [1, 2, 3]
    assert [n["diameter"] for n in first["nodules"]] == [5.0, 8.0, 4.0]


def test_report_input_reads_without_business_writes_or_store_dependency(
    entity_db, monkeypatch
):
    import martin.memory.store as memory_store

    def unavailable_store(*args, **kwargs):
        pytest.fail("Report fact projection must not read or write the memory Store")

    monkeypatch.setattr(memory_store, "get_default_store", unavailable_store)
    thread_id = _thread(entity_db)
    with connect(entity_db) as connection:
        before = list(connection.iterdump())

    assert _build(entity_db, "D001", thread_id)["nodules"][0]["diameter"] == 8.0

    with connect(entity_db) as connection:
        assert list(connection.iterdump()) == before


def test_report_input_rechecks_owner_and_revoked_patient_access(entity_db):
    thread_id = _thread(entity_db)
    with pytest.raises(AccessDeniedError):
        _build(entity_db, "D002", thread_id)
    assert _build(entity_db, "D001", thread_id) is not None
    with transaction(entity_db) as connection:
        connection.execute(
            "DELETE FROM doctor_patient_access WHERE doctor_id = 'D001'"
        )
    with pytest.raises(AccessDeniedError):
        _build(entity_db, "D001", thread_id)


def test_report_input_accepts_read_only_access_and_rejects_missing_thread(entity_db):
    thread_id = _thread(entity_db)
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE doctor_patient_access SET access_level = 'read_only' "
            "WHERE doctor_id = 'D001'"
        )

    assert _build(entity_db, "D001", thread_id)["source_case_id"] == "C002"
    with pytest.raises(EntityNotFoundError):
        _build(entity_db, "D001", "missing-thread")


def test_scoped_report_tool_ignores_model_case_and_measurements(entity_db, monkeypatch):
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.agent.tools import generate_report, reset_case_context, set_case_context

    received = _capture_chain(monkeypatch)
    context = CaseContext.from_dict({"patient_info": {"age": 62}})
    context_token = set_case_context(context)
    scope_token = set_report_scope("D001", _thread(entity_db))
    try:
        assert generate_report.invoke({
            "detection_result": json.dumps({
                "case_id": "C003", "nodules": [{"diameter": 99, "anatomy": "LLL"}],
            }),
            "case_context": json.dumps({"patient_info": {"age": 99}}),
        }) == "合成病例报告"
    finally:
        reset_report_scope(scope_token)
        reset_case_context(context_token)

    result, kwargs = received[0]
    assert result["source_case_id"] == "C002"
    assert result["nodules"][0]["diameter"] == 8.0
    assert result["nodules"][0]["anatomy"] == "RUL"
    assert kwargs["case_context"]["patient_info"]["age"] == 62
    assert context.nodules == []
    assert context.detection_completed is False


def test_unscoped_report_tool_keeps_standalone_detector_contract(monkeypatch):
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.agent.tools import generate_report
    from martin.services.report_input_service import ReportInputService

    def forbidden_business_read(*args):
        pytest.fail("A standalone detector report has no authorized business scope")

    monkeypatch.setattr(ReportInputService, "build", forbidden_business_read)
    received = _capture_chain(monkeypatch)
    scope_token = set_report_scope(None, None)
    detection = {"image": "synthetic.nii.gz", "nodules": [{"diameter": 4.5}]}
    try:
        assert generate_report.invoke({"detection_result": json.dumps(detection)}) == (
            "合成病例报告"
        )
    finally:
        reset_report_scope(scope_token)

    assert received[0][0]["image"] == "synthetic.nii.gz"
    assert received[0][0]["nodules"][0]["diameter"] == 4.5


@pytest.mark.parametrize(
    "status,finding_type",
    (("draft", "nodule"), ("superseded", "nodule"), ("confirmed", "effusion")),
)
def test_scoped_report_does_not_revive_checkpoint_after_finding_is_filtered(
    entity_db, monkeypatch, status, finding_type
):
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.agent.tools import generate_report, reset_case_context, set_case_context

    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE findings SET status = ?, finding_type = ? WHERE id = 'F002'",
            (status, finding_type),
        )
    received = _capture_chain(monkeypatch)
    context = CaseContext.from_dict({
        "nodules": [{"index": 1, "diameter": 8.0, "score": 0.9}],
        "detection_completed": True,
    })
    context_token = set_case_context(context)
    scope_token = set_report_scope("D001", _thread(entity_db))
    try:
        assert generate_report.invoke({}) == "合成病例报告"
    finally:
        reset_report_scope(scope_token)
        reset_case_context(context_token)

    report_input = received[0][0]
    assert report_input["source"] == "insufficient_data"
    assert report_input["nodules"] == []
    assert report_input["total_nodules"] == 0
    assert report_input["detection_completed"] is False
    assert context.nodules[0]["diameter"] == 8.0


def test_scoped_report_does_not_use_stale_data_when_business_db_fails(
    entity_db, monkeypatch
):
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.agent.tools import generate_report, reset_case_context, set_case_context
    from martin.services.report_input_service import ReportInputService

    def failed_read(*args):
        raise sqlite3.DatabaseError("synthetic current-case failure")

    monkeypatch.setattr(ReportInputService, "build", failed_read)
    received = _capture_chain(monkeypatch)
    context = CaseContext.from_dict({"nodules": [{"diameter": 99.0}]})
    context_token = set_case_context(context)
    scope_token = set_report_scope("D001", _thread(entity_db))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            generate_report.invoke({})
    finally:
        reset_report_scope(scope_token)
        reset_case_context(context_token)

    assert received == []


@pytest.mark.parametrize("graph_fails", (False, True))
def test_agent_scopes_report_tool_and_restores_outer_context(
    entity_db, monkeypatch, graph_fails
):
    from martin.agent.agent import AgentExecutor
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import (
        current_report_scope, reset_report_scope, set_report_scope,
    )
    from martin.agent.tools import (
        generate_report, get_case_context, reset_case_context, set_case_context,
    )

    received = _capture_chain(monkeypatch)
    thread_id = _thread(entity_db)
    executor = object.__new__(AgentExecutor)
    executor.thread_id = thread_id
    executor.doctor_id = "D001"
    executor.verbose = False
    executor.case_context = CaseContext()
    executor.report_preferences = {}
    executor._agent = MagicMock()

    def invoke_graph(*args, **kwargs):
        scope = current_report_scope()
        assert scope.doctor_id == "D001"
        assert scope.thread_id == thread_id
        assert get_case_context() is executor.case_context
        if graph_fails:
            raise RuntimeError("synthetic graph failure")
        report = generate_report.invoke({})
        return {"messages": [AIMessage(content=report)]}

    executor._agent.invoke.side_effect = invoke_graph
    outer_context = CaseContext()
    context_token = set_case_context(outer_context)
    scope_token = set_report_scope("outer-doctor", "outer-thread")
    try:
        output = executor.invoke({"input": "生成报告"})["output"]
        assert current_report_scope().thread_id == "outer-thread"
        assert get_case_context() is outer_context
    finally:
        reset_report_scope(scope_token)
        reset_case_context(context_token)

    if graph_fails:
        assert "synthetic graph failure" in output
        assert received == []
    else:
        assert output == "合成病例报告"
        assert received[0][0]["source_case_id"] == "C002"
        assert executor.case_context.nodules == []


def test_report_api_requires_login_and_server_thread(entity_client, report_saver):
    assert entity_client.post(
        "/api/report/generate", json={"session_id": "anything"},
    ).status_code == 401
    _login(entity_client)
    assert entity_client.post("/api/report/generate", json={}).status_code == 422
    assert entity_client.post(
        "/api/report/generate", json={"session_id": "missing-thread"},
    ).status_code == 404


def test_report_api_rejects_another_doctors_thread(
    entity_client, entity_db, report_saver, monkeypatch
):
    thread_id = _thread(entity_db)
    received = _capture_chain(monkeypatch)
    _login(entity_client, "b")

    response = entity_client.post(
        "/api/report/generate", json={"session_id": thread_id},
    )

    assert response.status_code == 403
    assert received == []
    assert "F002" not in response.text


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_report_api_passes_business_finding_to_model_without_ct(
    entity_client, entity_db, report_saver, monkeypatch, report_type
):
    received = _capture_chain(monkeypatch)
    _login(entity_client)
    thread_id = _thread(entity_db)

    response = entity_client.post(
        "/api/report/generate",
        json={
            "session_id": thread_id,
            "report_type": report_type,
            "detection_result": {"case_id": "C003", "nodules": [{"diameter": 99}]},
            "case_context": {"patient_info": {"age": 99}},
        },
    )

    assert response.status_code == 200
    assert response.json()["report_type"] == report_type
    result, kwargs = received[0]
    assert result["source_case_id"] == "C002"
    assert result["nodules"][0]["anatomy"] == "RUL"
    assert result["nodules"][0]["observed_at"] == CURRENT_OBSERVED_AT
    assert result["nodules"][0]["diameter"] == 8.0
    assert kwargs["case_context"]["patient_info"]["age"] is None
    assert "2026-06-01" not in json.dumps(result)


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_report_api_template_fallback_contains_current_finding_without_ct(
    entity_client, entity_db, report_saver, monkeypatch, report_type
):
    import martin.agent.tools as tools

    def unavailable_model(*args, **kwargs):
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(tools, "chain_generate_report", unavailable_model)
    _login(entity_client)

    response = entity_client.post(
        "/api/report/generate",
        json={"session_id": _thread(entity_db), "report_type": report_type},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert "RUL" in report
    assert "2026-09-01" in report
    assert "8.00" in report
    assert "2026-06-01" not in report
    assert "0.00%" not in report
    assert "未提供" in report


def test_report_api_db_read_failure_returns_503_before_model(
    entity_client, entity_db, report_saver, monkeypatch
):
    from martin.services.report_input_service import ReportInputService

    def failed_read(*args):
        raise sqlite3.DatabaseError("synthetic current-case failure")

    received = _capture_chain(monkeypatch)
    monkeypatch.setattr(ReportInputService, "build", failed_read)
    _login(entity_client)

    response = entity_client.post(
        "/api/report/generate", json={"session_id": _thread(entity_db)},
    )

    assert response.status_code == 503
    assert received == []
    assert "synthetic current-case failure" not in response.text


def test_report_api_restores_outer_scope_after_database_error(
    entity_db, report_saver, monkeypatch
):
    from fastapi import HTTPException

    from api.models import ReportRequest
    from api.routers.report import generate_case_report
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import (
        current_report_scope, reset_report_scope, set_report_scope,
    )
    from martin.agent.tools import (
        get_case_context, reset_case_context, set_case_context,
    )
    from martin.auth.session_service import DoctorIdentity
    from martin.services.report_input_service import ReportInputService

    def failed_read(*args):
        raise sqlite3.DatabaseError("synthetic current-case failure")

    monkeypatch.setattr(ReportInputService, "build", failed_read)
    outer_context = CaseContext()
    context_token = set_case_context(outer_context)
    scope_token = set_report_scope("outer-doctor", "outer-thread")
    try:
        with pytest.raises(HTTPException) as error:
            generate_case_report(
                ReportRequest(session_id=_thread(entity_db)),
                DoctorIdentity("D001", "doctor_a", "Doctor A"),
            )
        assert error.value.status_code == 503
        assert current_report_scope().thread_id == "outer-thread"
        assert get_case_context() is outer_context
    finally:
        reset_report_scope(scope_token)
        reset_case_context(context_token)


@pytest.mark.parametrize("detection_state", ("not_detected", "empty", "nodule"))
def test_report_api_restores_detector_context_after_sqlite_restart(
    entity_client, entity_db, tmp_path, monkeypatch, detection_state
):
    import api.routers.report as report_router
    import martin.agent.sessions as sessions

    _login(entity_client, "b")
    thread_id = _thread(entity_db, "D002", "C003")
    has_detection = detection_state != "not_detected"
    context = {
        "patient_info": {"age": 57},
        "image_info": {"filename": "synthetic-restored.nii.gz"},
        "nodules": (
            [{"index": 1, "diameter": 4.0}] if detection_state == "nodule" else []
        ),
        "detection_completed": has_detection,
    }
    checkpoint_path = tmp_path / "report-checkpoints.sqlite"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": str(uuid.uuid4()),
        "ts": "2026-09-30T00:00:00Z",
        "channel_values": {"messages": [], "case_context": context},
        "channel_versions": {"case_context": 1},
        "versions_seen": {},
    }
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        saver.put(
            config, checkpoint, {"source": "input", "step": 0}, {"case_context": 1}
        )
    received = _capture_chain(monkeypatch)

    with SqliteSaver.from_conn_string(str(checkpoint_path)) as restarted_saver:
        monkeypatch.setattr(
            sessions, "get_default_checkpointer", lambda: restarted_saver
        )
        monkeypatch.setattr(
            report_router, "get_default_checkpointer", lambda: restarted_saver,
            raising=False,
        )
        response = entity_client.post(
            "/api/report/generate",
            json={
                "session_id": thread_id,
                "detection_result": {"nodules": [{"diameter": 99.0}]},
                "case_context": {"patient_info": {"age": 99}},
            },
        )

    assert response.status_code == 200
    result, kwargs = received[0]
    assert kwargs["case_context"]["patient_info"]["age"] == 57
    assert result["detection_completed"] is has_detection
    if has_detection:
        assert result.get("source") != "insufficient_data"
        if detection_state == "nodule":
            assert result["nodules"][0]["diameter"] == 4.0
        else:
            assert result["nodules"] == []
    else:
        assert result["nodules"] == []
        assert result["source"] == "insufficient_data"


@pytest.mark.parametrize("detection_state", ("not_detected", "empty", "nodule"))
def test_rest_chat_cannot_replace_checkpoint_report_input_with_browser_measurements(
    entity_client, entity_db, report_saver, monkeypatch, detection_state
):
    import martin.agent.agent as agent_module
    import martin.agent.audit as audit_module
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.agent.tools import generate_report, reset_case_context, set_case_context

    _login(entity_client, "b")
    thread_id = _thread(entity_db, "D002", "C003")
    trusted_nodules = (
        [{"index": 1, "diameter": 8.0}] if detection_state == "nodule" else []
    )
    trusted_completed = detection_state != "not_detected"
    restored = CaseContext.from_dict({
        "nodules": trusted_nodules,
        "detection_completed": trusted_completed,
    })
    received = _capture_chain(monkeypatch)

    class FakeAgent:
        case_context = restored

        def invoke(self, inputs):
            assert self.case_context.nodules == trusted_nodules
            assert self.case_context.detection_completed is trusted_completed
            context_token = set_case_context(self.case_context)
            scope_token = set_report_scope("D002", thread_id)
            try:
                report = generate_report.invoke({})
            finally:
                reset_report_scope(scope_token)
                reset_case_context(context_token)
            return {"output": report, "intermediate_steps": []}

    monkeypatch.setattr(agent_module, "create_agent", lambda **kwargs: FakeAgent())
    monkeypatch.setattr(audit_module, "AuditLogger", MagicMock())

    response = entity_client.post(
        "/api/agent/chat",
        json={
            "session_id": thread_id,
            "user_message": "生成报告",
            "case_context": {
                "nodules": [{"index": 1, "diameter": 99.0}],
                "detection_completed": True,
            },
        },
    )

    assert response.status_code == 200
    report_input = received[0][0]
    assert report_input["nodules"] == trusted_nodules
    assert report_input["detection_completed"] is trusted_completed
    assert response.json()["case_context"]["nodules"] == trusted_nodules
    assert "99.0" not in json.dumps(report_input)
