"""T06-T10: source graphs, durable jobs and dispatch races using synthetic data."""

import threading
from copy import deepcopy
from types import SimpleNamespace

import pytest

from martin.db import transaction
from martin.memory.governance_jobs import GovernanceJobs, _jobs_ns
from martin.memory.models import MemoryCandidate
from martin.memory.namespaces import records_ns
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.memory.store import close_default_store
from martin.memory.summaries import SummaryService, summaries_ns
from martin.memory.writer import MemoryWriter
from martin.repositories.access import AccessRepository
from martin.services.access_service import AccessDeniedError
from martin.services.thread_service import ThreadService


def count(text):
    return len(text.encode("utf-8"))


def scope_for(db, doctor="D001", case="C002"):
    return authorize_scope(doctor, ThreadService(db).create_thread(doctor, case), db)


def source(scope, marker):
    return {
        "kind": "message",
        "actor_id": scope.doctor_id,
        "actor_role": "doctor",
        "message_id": marker,
        "thread_id": scope.thread_id,
    }


def save(
    writer, scope, text, key, *, kind="historical_discussion", observed_at="2026-06-01"
):
    return writer.write(
        scope,
        [MemoryCandidate(kind, text, key, observed_at=observed_at)],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=source(scope, key),
    ).records[0]


@pytest.fixture
def runtime(entity_db):
    scope = scope_for(entity_db)
    with transaction(entity_db) as connection:
        connection.execute("UPDATE patients SET sex='male' WHERE id='P001'")
        connection.execute("UPDATE cases SET age_at_encounter_years=55 WHERE id='C002'")
    service = MemoryService(entity_db)
    writer = MemoryWriter(service, SimpleNamespace(sync=lambda *args, **kwargs: None))
    for index, text in enumerate(
        (
            "第一次讨论：等待原始影像复核",
            "第二次讨论：等待病理，未作确认诊断",
            "第三次讨论：医生决定观察并保留理由",
        )
    ):
        save(writer, scope, text, "source-" + str(index))
    return service, writer, scope, SummaryService(service)


def build(summary, scope, **kwargs):
    return summary.rebuild(
        scope,
        token_budget=kwargs.pop("token_budget", 6000),
        token_counter=count,
        **kwargs,
    )


def queue(jobs, scope, **kwargs):
    return jobs.enqueue(
        scope,
        min_sources=kwargs.pop("min_sources", 3),
        min_tokens=kwargs.pop("min_tokens", 12000),
        token_counter=count,
        **kwargs,
    )


def run(jobs, scope, **kwargs):
    return jobs.run(
        scope,
        max_jobs=4,
        max_attempts=kwargs.pop("max_attempts", 3),
        summary_token_budget=6000,
        token_counter=count,
    )


def test_t06_threshold_enqueues_durably_then_reopens_and_runs_idempotently(runtime):
    service, writer, scope, summaries = runtime
    jobs = GovernanceJobs(service)
    assert not queue(jobs, scope, min_sources=4)["queued"]
    queued = queue(jobs, scope)
    assert queued["queued"]
    assert queue(jobs, scope)["job_id"] == queued["job_id"]
    assert (
        summaries.detailed_for_task(
            scope, "历史讨论原因", token_budget=6000, token_counter=count
        )["error_code"]
        == "summary_not_built"
    )
    close_default_store()
    fresh = GovernanceJobs(MemoryService(service.db_path))
    results = run(fresh, scope)
    assert results[0]["status"] == "completed"
    assert run(fresh, scope) == []
    assert len(service.list_records(scope)) == 3
    payload = summaries.detailed_for_task(
        scope, "历史讨论原因", token_budget=6000, token_counter=count
    )
    assert payload["available"] and len(payload["source_memory_ids"]) == 3
    assert payload["method"] == "extractive_raw_records_v1"
    assert summaries.validate_materialized(scope, payload)


def test_t06_token_trigger_and_policy_version_have_independent_jobs(runtime):
    service, writer, scope, summaries = runtime
    jobs = GovernanceJobs(service)
    first = queue(jobs, scope, min_sources=20, min_tokens=10, policy_version="v1")
    second = queue(jobs, scope, min_sources=20, min_tokens=10, policy_version="v2")
    assert first["queued"] and second["queued"]
    assert first["job_id"] != second["job_id"]
    assert len(jobs.list_jobs(scope)) == 2


def test_t07_retraction_atomically_stales_summary_and_cache_cannot_reenter(runtime):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)
    target = payload["source_memory_ids"][0]
    service.retract_record(scope, target, provenance=source(scope, "withdraw"))
    row = service._store().get(summaries_ns(scope), payload["summary_id"]).value
    assert row["status"] == "stale"
    assert not summaries.validate_materialized(scope, payload)
    refused = summaries.materialize(
        scope, payload["summary_id"], token_budget=6000, token_counter=count
    )
    assert not refused["available"] and refused["error_code"] == "summary_stale"
    replacement = build(summaries, scope)
    assert replacement["available"] and replacement["version"] == payload["version"] + 1
    assert target not in replacement["source_memory_ids"]
    assert (
        service.get_record(scope, target, include_inactive=True)["status"]
        == "retracted"
    )


def test_t07_retraction_failure_rolls_back_both_source_and_summary(runtime):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)
    target = payload["source_memory_ids"][0]
    store = service._store()
    store.conn.execute(
        "CREATE TRIGGER fail_summary_invalidation BEFORE INSERT ON store WHEN NEW.key LIKE 'summary:%' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
    )
    store.conn.commit()
    with pytest.raises(Exception):
        service.retract_record(scope, target, provenance=source(scope, "withdraw"))
    store.conn.execute("DROP TRIGGER fail_summary_invalidation")
    store.conn.commit()
    close_default_store()
    assert service.get_record(scope, target)["status"] == "active"
    assert summaries.validate_materialized(scope, payload)


def test_t07_dispatch_guard_serializes_in_process_retraction(runtime):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)
    attempted, finished = threading.Event(), threading.Event()

    def retract():
        attempted.set()
        service.retract_record(
            scope, payload["source_memory_ids"][0], provenance=source(scope, "race")
        )
        finished.set()

    with summaries.verified_for_injection(scope, payload) as verified:
        assert verified
        worker = threading.Thread(target=retract)
        worker.start()
        assert attempted.wait(1)
        assert not finished.wait(0.05)
    worker.join(timeout=3)
    assert finished.is_set()
    assert not summaries.validate_materialized(scope, payload)


def test_t07_external_connection_change_is_detected_without_invalidation_hook(runtime):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)
    target = payload["source_memory_ids"][0]
    # Simulate another connection changing the source while an old cache remains.
    from langgraph.store.sqlite import SqliteStore

    from martin.memory.store import get_memory_db_path

    with SqliteStore.from_conn_string(str(get_memory_db_path())) as other:
        other.setup()
        row = other.get(records_ns(scope.doctor_id, scope.patient_id), target).value
        other.put(
            records_ns(scope.doctor_id, scope.patient_id),
            target,
            dict(row, status="retracted"),
        )
    assert not summaries.validate_materialized(scope, payload)
    assert (
        summaries.materialize(
            scope, payload["summary_id"], token_budget=6000, token_counter=count
        )["error_code"]
        == "summary_stale"
    )


def test_t08_new_version_reuses_only_raw_sources_and_explicit_revision_blocks_old(
    runtime,
):
    service, writer, scope, summaries = runtime
    first = build(summaries, scope)
    target = first["source_memory_ids"][0]
    revised = writer.revise(
        scope,
        target,
        MemoryCandidate("historical_discussion", "医生更正：影像仍待复核"),
        provenance=source(scope, "revision"),
    ).records[0]
    assert not summaries.validate_materialized(scope, first)
    second = build(summaries, scope)
    assert revised["memory_id"] in second["source_memory_ids"]
    assert target not in second["source_memory_ids"]
    assert set(second["source_memory_ids"]).issubset(
        {record["memory_id"] for record in service.list_records(scope)}
    )
    assert first["summary_id"] not in second["source_memory_ids"]
    assert "医生更正：影像仍待复核" in second["text"]


def test_t08_job_version_cas_rejects_sources_changed_after_enqueue(runtime):
    service, writer, scope, summaries = runtime
    jobs = GovernanceJobs(service)
    queue(jobs, scope)
    save(writer, scope, "新讨论：新增待复核事项", "new-source")
    result = run(jobs, scope)[0]
    assert result["status"] == "obsolete" and result["error_code"] == "source_changed"
    assert service._store().get(summaries_ns(scope), "head:" + scope.case_id) is None
    queue(jobs, scope)
    assert run(jobs, scope)[0]["status"] == "completed"


def test_t08_extractor_source_change_does_not_publish_obsolete_summary(
    runtime, monkeypatch
):
    service, writer, scope, summaries = runtime
    eligible = summaries.eligible_sources
    calls = 0

    def change_during_build(active_scope):
        nonlocal calls
        calls += 1
        if calls == 2:
            service.retract_record(
                scope,
                eligible(scope)[0]["memory_id"],
                provenance=source(scope, "changed"),
            )
        return eligible(active_scope)

    monkeypatch.setattr(summaries, "eligible_sources", change_during_build)
    assert build(summaries, scope)["error_code"] == "source_changed"
    assert service._store().get(summaries_ns(scope), "head:" + scope.case_id) is None


def test_t09_minimal_background_is_business_only_and_long_summary_is_on_demand(runtime):
    service, writer, scope, summaries = runtime
    save(writer, scope, "口述过敏待核实，不应默认背景", "claim", kind="clinical_claim")
    service.save_case_memory(
        scope.doctor_id, scope.case_id, "legacy", {"text": "无法定位医生的旧讨论"}
    )
    minimal = summaries.minimal_background(
        scope, token_budget=6000, token_counter=count
    )
    assert minimal["available"] and minimal["text"]
    assert "口述过敏" not in minimal["text"] and "旧讨论" not in minimal["text"]
    assert all(
        reference["authority"] == "confirmed_business_fact"
        for reference in minimal["sources"]
    )
    assert summaries.validate_materialized(scope, minimal)
    assert (
        summaries.minimal_background(None, token_budget=6000, token_counter=count)[
            "text"
        ]
        == ""
    )
    build(summaries, scope)
    simple = summaries.detailed_for_task(
        scope, "你好", token_budget=6000, token_counter=count
    )
    assert simple["available"] and not simple["requested"] and not simple["text"]
    detailed = summaries.detailed_for_task(
        scope, "为什么之前选择观察", token_budget=6000, token_counter=count
    )
    assert detailed["available"] and detailed["requested"]
    assert "口述过敏" not in detailed["text"] and "旧讨论" not in detailed["text"]


def test_t09_background_source_update_and_text_tampering_are_detected(runtime):
    service, writer, scope, summaries = runtime
    background = summaries.minimal_background(
        scope, token_budget=6000, token_counter=count
    )
    forged = dict(background, text=background["text"] + "已确认药物过敏")
    assert not summaries.validate_materialized(scope, forged)
    with transaction(service.db_path) as connection:
        connection.execute(
            "UPDATE patients SET sex='female' WHERE id=?", (scope.patient_id,)
        )
    assert not summaries.validate_materialized(scope, background)


def test_t10_governance_keeps_all_business_observations_and_dates(runtime):
    service, writer, scope, summaries = runtime
    with transaction(service.db_path) as connection:
        before = [
            dict(row)
            for row in connection.execute("SELECT * FROM findings ORDER BY id")
        ]
    jobs = GovernanceJobs(service)
    jobs.periodic(
        [scope],
        min_sources=3,
        min_tokens=12000,
        token_counter=count,
        summary_token_budget=6000,
        max_jobs=4,
        max_attempts=3,
    )
    with transaction(service.db_path) as connection:
        after = [
            dict(row)
            for row in connection.execute("SELECT * FROM findings ORDER BY id")
        ]
    assert before == after
    assert (
        service.snapshot_for_thread(scope.doctor_id, scope.thread_id)
        .historical_observations[0]["observed_at"]
        .startswith("2026-06-01")
    )


def test_summary_doctor_patient_case_scope_cannot_be_forged(runtime, entity_db):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D002", "P001")
        AccessRepository(connection).grant("D001", "P002")
    for other in (
        scope_for(entity_db, doctor="D002"),
        scope_for(entity_db, case="C003"),
        scope_for(entity_db, case="C001"),
    ):
        assert not summaries.materialize(
            other, payload["summary_id"], token_budget=6000, token_counter=count
        )["available"]
        assert not summaries.validate_materialized(other, payload)
        assert all(
            record["case_id"] == other.case_id
            for record in summaries.eligible_sources(other)
        )
    with transaction(entity_db) as connection:
        AccessRepository(connection).revoke("D001", "P001")
    with pytest.raises(AccessDeniedError):
        summaries.validate_materialized(scope, payload)


def test_source_graph_and_projection_tampering_fail_closed(runtime):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)
    namespace = summaries_ns(scope)
    original = service._store().get(namespace, payload["summary_id"]).value
    variants = []
    bad = deepcopy(original)
    bad["source_memory_ids"][0] = original["summary_id"]
    variants.append(bad)
    bad = deepcopy(original)
    bad["segments"][0]["text"] += "确认诊断"
    variants.append(bad)
    bad = deepcopy(original)
    bad["sources"][0]["doctor_id"] = "D002"
    variants.append(bad)
    for variant in variants:
        service._store().put(namespace, payload["summary_id"], variant)
        assert not summaries.validate_materialized(scope, payload)
        assert not summaries.materialize(
            scope, payload["summary_id"], token_budget=6000, token_counter=count
        )["available"]


def test_summary_budget_omits_complete_sources_with_explicit_coverage(runtime):
    service, writer, scope, summaries = runtime
    assert (
        build(summaries, scope, token_budget=1)["error_code"]
        == "summary_budget_exceeded"
    )
    payload = build(summaries, scope, token_budget=350)
    assert payload["available"] and count(payload["text"]) <= 350
    assert payload["omitted"] > 0
    assert len(payload["omitted_source_memory_ids"]) == payload["omitted"]
    assert summaries.validate_materialized(scope, payload)
    expanded = build(summaries, scope, token_budget=6000)
    assert expanded["version"] > payload["version"] and not expanded["omitted"]


def test_job_failure_retries_are_bounded_and_running_crash_is_recoverable(
    runtime, monkeypatch
):
    service, writer, scope, summaries = runtime
    jobs = GovernanceJobs(service)
    queued = queue(jobs, scope)
    namespace = _jobs_ns(scope)
    job = service._store().get(namespace, queued["job_id"]).value
    service._store().put(
        namespace, queued["job_id"], dict(job, status="running", attempts=1)
    )
    original = jobs.summaries.rebuild

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic private text must not enter job history")

    monkeypatch.setattr(jobs.summaries, "rebuild", fail)
    result = run(jobs, scope, max_attempts=3)[0]
    assert result["status"] == "queued" and result["attempts"] == 2
    assert run(jobs, scope, max_attempts=3)[0]["status"] == "failed"
    assert run(jobs, scope, max_attempts=3) == []
    assert not queue(jobs, scope)["queued"]
    assert "private text" not in str(jobs.list_jobs(scope))
    monkeypatch.setattr(jobs.summaries, "rebuild", original)


def test_job_claim_cas_does_not_overwrite_cancelled_work(runtime, monkeypatch):
    service, writer, scope, summaries = runtime
    jobs = GovernanceJobs(service)
    queued = queue(jobs, scope)
    original = jobs.summaries.rebuild

    def cancel_during_processing(*args, **kwargs):
        row = service._store().get(_jobs_ns(scope), queued["job_id"]).value
        service._store().put(
            _jobs_ns(scope), queued["job_id"], dict(row, status="cancelled")
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs.summaries, "rebuild", cancel_during_processing)
    assert run(jobs, scope)[0]["status"] == "cas_conflict"
    assert jobs.list_jobs(scope)[0]["status"] == "cancelled"
    assert service._store().get(summaries_ns(scope), "head:" + scope.case_id) is None


def test_source_store_unavailable_returns_no_cached_summary(runtime, monkeypatch):
    service, writer, scope, summaries = runtime
    payload = build(summaries, scope)

    def fail(*args, **kwargs):
        raise OSError("synthetic store failure")

    monkeypatch.setattr(service, "get_record", fail)
    assert not summaries.validate_materialized(scope, payload)
    result = summaries.materialize(
        scope, payload["summary_id"], token_budget=6000, token_counter=count
    )
    assert not result["available"] and not result["text"]


def test_counter_missing_and_invalid_triggers_do_not_disable_limits(runtime):
    service, writer, scope, summaries = runtime
    with pytest.raises(ValueError):
        summaries.rebuild(scope, token_budget=6000, token_counter=None)
    with pytest.raises(ValueError):
        queue(GovernanceJobs(service), scope, min_sources=0)


def test_writer_automatically_enqueues_at_policy_threshold_and_background_processes(
    runtime, monkeypatch
):
    service, writer, scope, summaries = runtime
    from martin.memory.budget_policy import BudgetPolicy, PolicyService
    from martin.memory.governance_jobs import process_pending

    monkeypatch.setattr(
        PolicyService, "current", lambda self: BudgetPolicy(summary_trigger_count=4)
    )
    saved = writer.write(
        scope,
        [MemoryCandidate("historical_discussion", "第四次讨论：仍需医生复核", "four")],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=source(scope, "four"),
    )
    assert saved.governance_job["queued"]
    assert (
        summaries.detailed_for_task(
            scope, "历史讨论", token_budget=6000, token_counter=count
        )["error_code"]
        == "summary_not_built"
    )
    assert process_pending(scope.doctor_id, scope.thread_id)[0]["status"] == "completed"
    assert process_pending(scope.doctor_id, scope.thread_id) == []
    assert summaries.detailed_for_task(
        scope, "历史讨论", token_budget=6000, token_counter=count
    )["available"]


def test_queue_fault_does_not_lose_original_source_and_is_reported(
    runtime, monkeypatch
):
    service, writer, scope, summaries = runtime

    def fail(*args, **kwargs):
        raise OSError("synthetic queue failure")

    monkeypatch.setattr(GovernanceJobs, "enqueue", fail)
    result = writer.write(
        scope,
        [MemoryCandidate("historical_discussion", "源记录仍应保存", "persist")],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=source(scope, "persist"),
    )
    assert service.get_record(scope, result.records[0]["memory_id"])
    assert result.governance_job == {
        "queued": False,
        "error_code": "summary_queue_unavailable",
    }


def test_retracted_summary_rebuild_is_queued_even_below_initial_threshold(runtime):
    service, writer, scope, summaries = runtime
    from martin.memory.governance_jobs import process_pending

    payload = build(summaries, scope)
    service.retract_record(
        scope, payload["source_memory_ids"][0], provenance=source(scope, "withdraw")
    )
    jobs = GovernanceJobs(service).list_jobs(scope)
    assert (
        len(jobs) == 1
        and jobs[0]["status"] == "queued"
        and jobs[0]["source_count"] == 2
    )
    assert process_pending(scope.doctor_id, scope.thread_id)[0]["status"] == "completed"
    updated = summaries.detailed_for_task(
        scope, "历史讨论", token_budget=6000, token_counter=count
    )
    assert updated["available"] and len(updated["source_memory_ids"]) == 2


def test_valid_older_projection_explicitly_reports_added_sources(runtime):
    service, writer, scope, summaries = runtime
    first = build(summaries, scope)
    added = save(writer, scope, "后来新增讨论，不应被省略而冒称完整", "after-build")
    selected = summaries.materialize(
        scope, first["summary_id"], token_budget=6000, token_counter=count
    )
    assert selected["available"]
    assert selected["newer_source_memory_ids"] == [added["memory_id"]]
    assert added["memory_id"] in selected["omitted_source_memory_ids"]
    assert selected["omitted"] == 1


def test_summary_retains_structured_clinical_distinctions_as_doctor_context(runtime):
    service, writer, scope, summaries = runtime
    result = writer.write(
        scope,
        [
            MemoryCandidate(
                "clinical_decision",
                "同位置观察，关联待确认",
                "identity",
                data={
                    "lesion_id": "synthetic-distinct-lesion",
                    "association": "unconfirmed",
                },
                confidence=0.4,
            )
        ],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=source(scope, "identity"),
    )
    payload = build(summaries, scope)
    assert "synthetic-distinct-lesion" in payload["text"]
    assert '"association": "unconfirmed"' in payload["text"]
    reference = next(
        item
        for item in payload["sources"]
        if item["memory_id"] == result.records[0]["memory_id"]
    )
    assert reference["confidence"] == 0.4 and reference["authority"] == "doctor_context"
