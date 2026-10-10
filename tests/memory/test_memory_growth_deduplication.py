"""T01-T05: conservative growth control against isolated real source SQLite."""

from types import SimpleNamespace

import pytest

from martin.db import transaction
from martin.memory.models import MemoryCandidate
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.memory.store import close_default_store
from martin.memory.writer import MemoryWriter
from martin.repositories.access import AccessRepository
from martin.services.thread_service import ThreadService


def scope_for(db, *, doctor="D001", case="C002"):
    thread = ThreadService(db).create_thread(doctor, case)
    return authorize_scope(doctor, thread, db)


def source(scope, marker):
    return {
        "kind": "message",
        "actor_id": scope.doctor_id,
        "actor_role": "doctor",
        "thread_id": scope.thread_id,
        "message_id": marker,
    }


def save(writer, scope, candidate, marker="synthetic-source"):
    return writer.write(
        scope,
        [candidate],
        source_type="thread",
        source_id=scope.thread_id,
        provenance=source(scope, marker),
    )


@pytest.fixture
def runtime(entity_db):
    service = MemoryService(entity_db)
    writer = MemoryWriter(service, SimpleNamespace(sync=lambda *args, **kwargs: None))
    return service, writer, scope_for(entity_db)


def test_t01_exact_duplicate_preserves_distinct_sources_and_retry(runtime):
    service, writer, scope = runtime
    candidate = MemoryCandidate("workflow_preference", "以后报告先给结论")
    first = save(writer, scope, candidate, "human-one")
    second = save(writer, scope, candidate, "human-two")
    assert second.deduplicated == 1
    assert second.records[0]["memory_id"] == first.records[0]["memory_id"]
    references = second.records[0]["reinforced_sources"]
    assert references[0]["source_message_id"] == "human-two"
    assert second.records[0]["source_message_id"] == "human-one"
    assert (
        save(writer, scope, candidate, "human-two").records[0]["reinforced_sources"]
        == references
    )
    close_default_store()
    assert len(service.list_records(scope)) == 1
    assert len(service.list_records(scope)[0]["reinforced_sources"]) == 1


def test_t02_supported_synonyms_merge_across_authorized_threads(runtime, entity_db):
    service, writer, scope = runtime
    first = save(
        writer, scope, MemoryCandidate("workflow_preference", "以后报告先给结论"), "a"
    )
    later = scope_for(entity_db)
    second = save(
        writer, later, MemoryCandidate("workflow_preference", "今后报告结论前置"), "b"
    )
    assert second.deduplicated == 1
    assert second.decisions[0]["reason"] == "low_risk_equivalent"
    assert first.records[0]["memory_id"] == second.records[0]["memory_id"]
    assert len(service.list_records(later)) == 1
    assert second.records[0]["reinforced_sources"][0]["text"] == "今后报告结论前置"
    assert service.validate_record_source(later, second.records[0])


@pytest.mark.parametrize(
    "text",
    [
        "普通报告控制在200字以内",
        "复杂病例可以详细写",
        "以后报告不要先给结论",
        "2024年报告先给结论",
        "如果资料齐全报告先给结论",
        "报告先给结论并写出所有依据",
    ],
)
def test_t03_conditions_negation_dates_and_new_information_stay_independent(
    runtime, text
):
    service, writer, scope = runtime
    save(
        writer,
        scope,
        MemoryCandidate("workflow_preference", "以后报告先给结论", "style"),
        "a",
    )
    result = save(
        writer, scope, MemoryCandidate("workflow_preference", text, "style"), "b"
    )
    assert result.deduplicated == 0
    assert len(service.list_records(scope)) == 2
    assert all(record["status"] == "active" for record in service.list_records(scope))


@pytest.mark.parametrize(
    "kind",
    ["clinical_decision", "historical_discussion", "clinical_claim", "correction"],
)
@pytest.mark.parametrize("same_key", [True, False])
def test_t04_high_risk_similar_distinct_reasons_do_not_merge(runtime, kind, same_key):
    service, writer, scope = runtime
    save(
        writer,
        scope,
        MemoryCandidate(kind, "选择观察，因为需要复核影像", "reason-one"),
        "a",
    )
    key = "reason-one" if same_key else "reason-two"
    saved = save(
        writer, scope, MemoryCandidate(kind, "选择观察，因为需要等待病理", key), "b"
    )
    assert saved.deduplicated == 0
    assert saved.records[0]["supersedes"] is None
    assert len(service.list_records(scope)) == 2
    assert all(record["status"] == "active" for record in service.list_records(scope))


def test_t05_high_risk_different_dates_cases_and_unspecified_occurrences(
    runtime, entity_db
):
    service, writer, scope = runtime
    candidate = MemoryCandidate(
        "clinical_decision", "右上叶选择观察", "decision", observed_at="2024-06-01"
    )
    original = save(writer, scope, candidate, "a")
    different_date = MemoryCandidate(
        "clinical_decision", candidate.text, "decision", observed_at="2026-06-01"
    )
    save(writer, scope, different_date, "b")
    earlier_case = scope_for(entity_db, case="C001")
    save(writer, earlier_case, candidate, "c")
    unspecified = MemoryCandidate("clinical_decision", candidate.text, "decision")
    save(writer, scope, unspecified, "d")
    save(writer, scope, unspecified, "e")
    assert len(service.list_records(scope)) == 5
    assert (
        service.get_record(scope, original.records[0]["memory_id"])["status"]
        == "active"
    )


def test_t05_same_clinical_event_exact_duplicate_reinforces_without_promoting_authority(
    runtime,
):
    service, writer, scope = runtime
    candidate = MemoryCandidate(
        "clinical_claim", "医生陈述过敏待核实", "allergy", observed_at="2026-06-01"
    )
    save(writer, scope, candidate, "a")
    result = save(writer, scope, candidate, "b")
    assert result.deduplicated == 1
    assert result.records[0]["verification_status"] == "unverified"
    assert result.records[0]["data"]["business_fact_updated"] is False
    assert len(service.list_records(scope)) == 1


def test_explicit_revision_only_supersedes_requested_high_risk_record(runtime):
    service, writer, scope = runtime
    first = save(
        writer, scope, MemoryCandidate("clinical_claim", "声明一待核实", "claim"), "a"
    ).records[0]
    independent = save(
        writer, scope, MemoryCandidate("clinical_claim", "声明二待核实", "claim"), "b"
    ).records[0]
    revised = writer.revise(
        scope,
        first["memory_id"],
        MemoryCandidate("clinical_claim", "声明一更正待核实"),
        provenance=source(scope, "c"),
    ).records[0]
    assert revised["supersedes"] == first["memory_id"]
    assert service.get_record(scope, independent["memory_id"])["status"] == "active"
    assert service.get_record(scope, first["memory_id"]) is None
    assert len(service.list_records(scope)) == 2


def test_different_structured_lesions_and_explicit_cross_case_claim_revision(
    runtime, entity_db
):
    service, writer, scope = runtime
    for lesion in ("synthetic-L1", "synthetic-L2"):
        result = save(
            writer,
            scope,
            MemoryCandidate(
                "clinical_decision",
                "右上叶观察",
                "observe",
                data={"lesion_id": lesion},
                observed_at="2026-06-01",
            ),
            lesion,
        )
        assert result.deduplicated == 0
    assert len(service.list_records(scope)) == 2
    old_scope = scope_for(entity_db, case="C001")
    original = save(
        writer,
        old_scope,
        MemoryCandidate("clinical_claim", "既往口述待核实", "claim"),
        "old",
    ).records[0]
    revised = writer.revise(
        scope,
        original["memory_id"],
        MemoryCandidate("clinical_claim", "医生明确修订待核实口述"),
        provenance=source(scope, "current"),
    ).records[0]
    assert revised["supersedes"] == original["memory_id"]
    assert revised["revision"] == original["revision"] + 1
    assert service.get_record(scope, original["memory_id"]) is None


def test_duplicate_cannot_reinforce_with_assistant_or_foreign_scope(runtime, entity_db):
    service, writer, scope = runtime
    candidate = MemoryCandidate("workflow_preference", "以后报告先给结论")
    saved = save(writer, scope, candidate).records[0]
    with pytest.raises(ValueError):
        writer.write(
            scope,
            [candidate],
            source_type="thread",
            source_id=scope.thread_id,
            provenance=dict(source(scope, "bad"), actor_role="assistant"),
        )
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D002", "P001")
    other = scope_for(entity_db, doctor="D002")
    foreign = save(writer, other, candidate, "another-doctor").records[0]
    assert foreign["memory_id"] != saved["memory_id"]
    assert service.get_record(other, saved["memory_id"]) is None
    assert "reinforced_sources" not in service.get_record(scope, saved["memory_id"])


def test_retracted_preference_is_not_revived_by_synonym(runtime):
    service, writer, scope = runtime
    original = save(
        writer, scope, MemoryCandidate("workflow_preference", "以后报告先给结论"), "a"
    ).records[0]
    service.retract_record(
        scope, original["memory_id"], provenance=source(scope, "retract")
    )
    replacement = save(
        writer, scope, MemoryCandidate("workflow_preference", "今后报告结论前置"), "b"
    )
    assert replacement.deduplicated == 0
    assert replacement.records[0]["memory_id"] != original["memory_id"]
    assert replacement.records[0]["supersedes"] is None
    assert service.get_record(scope, original["memory_id"]) is None


def test_structured_report_preference_duplicate_preserves_source_and_corruption_fails_closed(
    runtime,
):
    service, writer, scope = runtime
    from martin.memory.namespaces import doctor_records_ns

    first = service.save_doctor_preference(
        scope.doctor_id,
        "report_style",
        {"max_words": 200},
        provenance=source(scope, "first"),
    )
    second = service.save_doctor_preference(
        scope.doctor_id,
        "report_style",
        {"max_words": 200},
        provenance=source(scope, "second"),
    )
    assert first["memory_id"] == second["memory_id"]
    assert second["reinforced_sources"][0]["source_message_id"] == "second"
    assert service.get_doctor_preferences(scope.doctor_id)["report_style"] == {
        "max_words": 200
    }
    second["reinforced_sources"][0]["provenance"]["actor_id"] = "D002"
    service._store().put(
        doctor_records_ns(scope.doctor_id), second["memory_id"], second
    )
    assert service.get_doctor_preferences(scope.doctor_id) == {}
