"""Budget policy governance and real capabilities on isolated synthetic SQLite."""

import json
import sqlite3
from copy import deepcopy

import pytest

from martin.auth.capabilities import is_budget_admin, set_budget_admin
from martin.db import init_schema, transaction
from martin.memory.budget_policy import (
    CONTEXT_HARD_MAX,
    CONTEXT_MIN,
    MAX_STAGE_BATCHES,
    POLICY_NS,
    VERSION_NS,
    BudgetPolicy,
    PolicyService,
    PolicyVersionConflict,
)
from martin.memory.scope import MemoryScope, authorize_scope
from martin.repositories.access import AccessRepository
from martin.repositories.users import UserRepository
from martin.services.access_service import AccessDeniedError, EntityNotFoundError
from martin.services.thread_service import ThreadService


@pytest.fixture
def policy_service(entity_db):
    set_budget_admin(
        "D001", True, operator_label="synthetic unit-test operator", db_path=entity_db
    )
    return PolicyService(db_path=entity_db)


def test_missing_policy_uses_bounded_safe_default(policy_service):
    info = policy_service.current_info()
    policy = policy_service.current()
    assert info["source"] == "safe_default"
    assert info["version"] == 0
    assert CONTEXT_MIN <= policy.context_window <= CONTEXT_HARD_MAX
    assert (
        policy.input_token_limit + policy.reserved_output + policy.safety_margin
        == policy.context_window
    )
    assert info["limits"]["context_max"] == CONTEXT_HARD_MAX
    assert policy_service._store().get(POLICY_NS, "current") is None


@pytest.mark.parametrize(
    "record",
    [
        {"schema_version": 99, "version": 4, "policy": BudgetPolicy().to_dict()},
        {"schema_version": 1, "version": 4, "policy": {"unknown_field": 1}},
        {
            "schema_version": 1,
            "version": 4,
            "policy": {"context_window": CONTEXT_HARD_MAX + 1},
        },
        {"schema_version": 1, "version": True, "policy": BudgetPolicy().to_dict()},
    ],
)
def test_invalid_stored_policy_cannot_disable_hard_cap(policy_service, record):
    policy_service._store().put(POLICY_NS, "current", record)
    info = policy_service.current_info()
    assert info["source"] == "safe_default"
    assert info["version"] == 0
    assert info["policy"]["context_window"] <= CONTEXT_HARD_MAX
    with pytest.raises(ValueError):
        policy_service.save("D001", BudgetPolicy().to_dict(), expected_version=0)
    assert policy_service._store().search(VERSION_NS) == []


def test_unavailable_store_uses_safe_default():
    class UnavailableStore:
        def get(self, *args):
            raise OSError("synthetic unavailable store")

    info = PolicyService(store=UnavailableStore()).current_info()
    assert info["source"] == "safe_default"
    assert info["policy"]["context_window"] <= CONTEXT_HARD_MAX


def test_save_assigns_server_version_and_preserves_audit(policy_service):
    candidate = BudgetPolicy().to_dict()
    candidate.update(version=1234, summary_trigger_count=15)
    saved = policy_service.save(
        "D001", candidate, expected_version=0, reason="synthetic scale adjustment"
    )
    assert saved["version"] == saved["policy"]["version"] == 1
    assert saved["source"] == "persisted"
    history = policy_service.versions("D001")
    assert len(history) == 1
    assert history[0]["actor_id"] == "D001"
    assert history[0]["created_at"]
    assert history[0]["reason"] == "synthetic scale adjustment"
    assert history[0]["before"] == BudgetPolicy().to_dict()
    assert history[0]["policy"]["summary_trigger_count"] == 15


def test_stale_save_is_rejected_without_extra_history(policy_service):
    candidate = BudgetPolicy().to_dict()
    policy_service.save("D001", candidate, expected_version=0)
    candidate["summary_trigger_count"] += 1
    with pytest.raises(PolicyVersionConflict):
        policy_service.save("D001", candidate, expected_version=0)
    assert policy_service.current_info()["version"] == 1
    assert len(policy_service.versions("D001")) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"context_window": CONTEXT_HARD_MAX + 1},
        {"context_window": CONTEXT_MIN - 1},
        {"context_window": True},
        {"context_window": float(CONTEXT_MIN)},
        {"reserved_output": 8193},
        {"safety_margin": 0},
        {"summary_trigger_count": 1},
        {"summary_trigger_tokens": 0},
        {"max_stage_batches": MAX_STAGE_BATCHES + 1},
        {"max_stage_seconds": 0},
        {"context_window": CONTEXT_MIN, "reserved_output": CONTEXT_MIN},
        {
            "context_window": CONTEXT_MIN,
            "reserved_output": 512,
            "safety_margin": 256,
            "summary_tokens": 8192,
        },
        {"category_quotas": {}},
        {"patient_id": "synthetic-forged-scope"},
    ],
)
def test_invalid_policy_does_not_create_version(policy_service, patch):
    candidate = BudgetPolicy().to_dict()
    candidate.update(patch)
    with pytest.raises(ValueError):
        policy_service.save("D001", candidate, expected_version=0)
    assert policy_service._store().get(POLICY_NS, "current") is None
    assert policy_service._store().search(VERSION_NS) == []


@pytest.mark.parametrize("weight", [True, 25.0, -1, 101, 26])
def test_invalid_quota_weight_or_total_is_rejected(policy_service, weight):
    candidate = BudgetPolicy().to_dict()
    candidate["category_quotas"]["default"] = {
        "history": 25,
        "rag": weight,
        "memory": 25,
        "summary": 25,
    }
    with pytest.raises(ValueError):
        policy_service.save("D001", candidate, expected_version=0)
    assert policy_service.current_info()["version"] == 0


def test_ordinary_doctor_cannot_save_read_history_or_rollback(policy_service):
    with pytest.raises(AccessDeniedError):
        policy_service.save("D002", BudgetPolicy().to_dict(), expected_version=0)
    with pytest.raises(AccessDeniedError):
        policy_service.versions("D002")
    with pytest.raises(AccessDeniedError):
        policy_service.rollback("D002", 0, expected_version=0)
    assert policy_service.current_info()["version"] == 0


def test_permission_revoked_before_commit_prevents_write(
    policy_service, entity_db, monkeypatch
):
    original_check = policy_service.can_manage
    checks = []

    def revoke_after_first_real_check(actor_id):
        allowed = original_check(actor_id)
        checks.append(allowed)
        if len(checks) == 1:
            set_budget_admin(
                "D001",
                False,
                operator_label="synthetic concurrent revoke",
                db_path=entity_db,
            )
        return allowed

    monkeypatch.setattr(policy_service, "can_manage", revoke_after_first_real_check)
    with pytest.raises(AccessDeniedError):
        policy_service.save("D001", BudgetPolicy().to_dict(), expected_version=0)
    assert policy_service._store().get(POLICY_NS, "current") is None
    assert policy_service._store().search(VERSION_NS) == []
    assert checks == [True, False]


def test_policy_and_history_write_roll_back_together(policy_service):
    store = policy_service._store()
    store.conn.execute("""CREATE TRIGGER fail_budget_history BEFORE INSERT ON store
           WHEN NEW.prefix = 'system.memory_budget_versions'
           BEGIN SELECT RAISE(ABORT, 'synthetic history failure'); END""")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="synthetic history failure"):
            policy_service.save("D001", BudgetPolicy().to_dict(), expected_version=0)
        assert store.get(POLICY_NS, "current") is None
        assert store.search(VERSION_NS) == []
    finally:
        store.conn.execute("DROP TRIGGER fail_budget_history")


def test_rollback_creates_new_audited_version_and_safe_default(policy_service):
    first = BudgetPolicy().to_dict()
    first["summary_trigger_count"] = 15
    policy_service.save("D001", first, expected_version=0, reason="first")
    second = deepcopy(first)
    second["summary_trigger_count"] = 20
    policy_service.save("D001", second, expected_version=1, reason="second")
    result = policy_service.rollback("D001", 1, expected_version=2, reason="restore")
    assert result["version"] == 3
    assert result["policy"]["summary_trigger_count"] == 15
    assert policy_service.versions("D001")[0]["reverted_from"] == 1
    result = policy_service.rollback("D001", 0, expected_version=3, reason="defaults")
    assert result["version"] == 4
    expected = BudgetPolicy().to_dict()
    expected["version"] = 4
    assert result["policy"] == expected
    assert policy_service.versions("D001")[0]["reverted_from"] == 0


def test_unknown_rollback_target_does_not_change_policy(policy_service):
    with pytest.raises(ValueError, match="not found"):
        policy_service.rollback("D001", 999, expected_version=0)
    assert policy_service.current_info()["version"] == 0


@pytest.fixture
def trace_scope(entity_db):
    thread = ThreadService(entity_db).create_thread("D001", "C001")
    return authorize_scope("D001", thread, entity_db)


@pytest.mark.parametrize(
    "field",
    [
        "text",
        "content",
        "messages",
        "prompt",
        "answer",
        "reasoning",
        "query",
        "user_input",
    ],
)
def test_trace_rejects_nested_clinical_text(policy_service, trace_scope, field):
    with pytest.raises(ValueError, match="clinical text"):
        policy_service.record_trace(
            trace_scope,
            {"items": [{"metadata": {field: "synthetic private content"}}]},
        )
    assert policy_service.latest_trace(trace_scope) is None


def test_trace_is_private_to_doctor_and_thread(policy_service, trace_scope, entity_db):
    other_thread = ThreadService(entity_db).create_thread("D001", "C002")
    other_scope = authorize_scope("D001", other_thread, entity_db)
    metrics = {
        "request_id": "synthetic-request",
        "policy_version": 0,
        "input_tokens": 100,
    }
    policy_service.record_trace(trace_scope, metrics)
    assert policy_service.latest_trace(trace_scope) == metrics
    assert policy_service.latest_trace(other_scope) is None
    forged = MemoryScope("D002", "P001", "C001", trace_scope.thread_id)
    with pytest.raises(AccessDeniedError):
        policy_service.latest_trace(forged)
    metrics["input_tokens"] = 999
    assert policy_service.latest_trace(trace_scope)["input_tokens"] == 100


def test_trace_read_rechecks_grant_after_store_lookup(
    policy_service, trace_scope, entity_db, monkeypatch
):
    policy_service.record_trace(trace_scope, {"request_id": "synthetic-request"})
    store = policy_service._store()
    original_get = store.get

    def revoke_during_lookup(*args, **kwargs):
        result = original_get(*args, **kwargs)
        with transaction(entity_db) as connection:
            AccessRepository(connection).revoke("D001", "P001")
        return result

    monkeypatch.setattr(store, "get", revoke_during_lookup)
    with pytest.raises(AccessDeniedError):
        policy_service.latest_trace(trace_scope)


def test_history_permission_revoked_during_read_prevents_return(
    policy_service, entity_db, monkeypatch
):
    policy_service.save("D001", BudgetPolicy().to_dict(), expected_version=0)
    store = policy_service._store()
    original_search = store.search

    def revoke_during_history_read(*args, **kwargs):
        records = original_search(*args, **kwargs)
        set_budget_admin(
            "D001", False, operator_label="synthetic history revoke", db_path=entity_db
        )
        return records

    monkeypatch.setattr(store, "search", revoke_during_history_read)
    with pytest.raises(AccessDeniedError):
        policy_service.versions("D001")


def test_budget_capability_defaults_off_and_preserves_role_and_patient_grants(
    entity_db,
):
    assert not is_budget_admin("D001", db_path=entity_db)
    assert not is_budget_admin("D002", db_path=entity_db)
    with transaction(entity_db) as connection:
        before_grants = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM doctor_patient_access ORDER BY doctor_id, patient_id"
            )
        ]
    set_budget_admin(
        "D002", True, operator_label="synthetic maintenance", db_path=entity_db
    )
    assert is_budget_admin("D002", db_path=entity_db)
    with transaction(entity_db) as connection:
        assert UserRepository(connection).get_by_id("D002")["role"] == "doctor"
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM doctor_patient_access ORDER BY doctor_id, patient_id"
            )
        ] == before_grants
        audit = connection.execute(
            "SELECT * FROM case_change_audit WHERE target_type='user_capability' AND target_id='D002'"
        ).fetchone()
        assert audit["action"] == "budget_admin_granted"
        assert json.loads(audit["before_json"]) == {"budget_admin": False}
        assert (
            json.loads(audit["after_json"])["operator_label"] == "synthetic maintenance"
        )
    set_budget_admin(
        "D002", False, operator_label="synthetic revoke", db_path=entity_db
    )
    assert not is_budget_admin("D002", db_path=entity_db)


def test_inactive_doctor_cannot_use_or_receive_budget_capability(entity_db):
    set_budget_admin(
        "D001", True, operator_label="synthetic maintenance", db_path=entity_db
    )
    with transaction(entity_db) as connection:
        UserRepository(connection).deactivate("D001")
    assert not is_budget_admin("D001", db_path=entity_db)
    assert not PolicyService(db_path=entity_db).can_manage("D001")
    with pytest.raises(EntityNotFoundError):
        set_budget_admin(
            "D001", True, operator_label="synthetic maintenance", db_path=entity_db
        )


def test_capability_and_maintenance_audit_commit_atomically(entity_db):
    with transaction(entity_db) as connection:
        connection.execute(
            """CREATE TRIGGER fail_capability_audit BEFORE INSERT ON case_change_audit
               WHEN NEW.target_type = 'user_capability'
               BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="synthetic audit failure"):
        set_budget_admin(
            "D001", True, operator_label="synthetic maintenance", db_path=entity_db
        )
    assert not is_budget_admin("D001", db_path=entity_db)
    with transaction(entity_db) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM case_change_audit").fetchone()[0]
            == 0
        )


def test_legacy_schema_fails_closed_and_additive_migration_preserves_user(tmp_path):
    path = tmp_path / "legacy-app.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('doctor')),
                password_hash TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        connection.execute(
            "INSERT INTO users VALUES ('legacy-id', 'synthetic', 'Synthetic Doctor', 'doctor', 'synthetic-hash', 1, 'before', 'before')"
        )
        original = connection.execute("SELECT * FROM users").fetchone()
    assert not is_budget_admin("legacy-id", db_path=path)
    with pytest.raises(ValueError, match="additive"):
        set_budget_admin(
            "legacy-id", True, operator_label="synthetic maintenance", db_path=path
        )
    init_schema(path)
    init_schema(path)
    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(users)")]
        assert columns.count("budget_admin") == 1
        migrated = connection.execute(
            "SELECT id, username, display_name, role, password_hash, is_active, created_at, updated_at FROM users"
        ).fetchone()
        assert migrated == original
        assert connection.execute("SELECT budget_admin FROM users").fetchone()[0] == 0
    assert not is_budget_admin("legacy-id", db_path=path)
    set_budget_admin(
        "legacy-id", True, operator_label="synthetic maintenance", db_path=path
    )
    assert is_budget_admin("legacy-id", db_path=path)
