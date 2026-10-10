"""Budget REST permissions and version contracts with isolated synthetic doctors."""

import pytest

from martin.auth.capabilities import set_budget_admin
from martin.db import transaction
from martin.memory.budget_policy import CONTEXT_HARD_MAX, BudgetPolicy, PolicyService
from martin.memory.scope import authorize_scope
from martin.repositories.users import UserRepository
from martin.services.thread_service import ThreadService


@pytest.fixture(autouse=True)
def real_budget_admin(entity_db):
    # Real capability, confined to the existing per-test synthetic business DB.
    set_budget_admin(
        "D001", True, operator_label="synthetic API-test operator", db_path=entity_db
    )


def _login(client, doctor="a"):
    result = client.post(
        "/api/auth/login",
        json={
            "username": f"doctor_{doctor}",
            "password": f"TestDoctor{doctor.upper()}!2026",
        },
    )
    assert result.status_code == 200


def _update(version=0, **policy_updates):
    policy = BudgetPolicy().to_dict()
    policy.update(policy_updates)
    return {"expected_version": version, "policy": policy, "reason": "synthetic change"}


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/policy", None),
        ("PUT", "/policy", _update()),
        ("GET", "/history", None),
        ("POST", "/rollback", {"expected_version": 0, "target_version": 0}),
        ("GET", "/trace?thread_id=synthetic-thread", None),
    ],
)
def test_budget_endpoints_require_session(entity_client, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    assert (
        entity_client.request(method, "/api/memory/budget" + path, **kwargs).status_code
        == 401
    )


def test_ordinary_doctor_cannot_change_policy_or_read_history(entity_client):
    _login(entity_client, "b")
    response = entity_client.get("/api/memory/budget/policy?can_manage=true")
    assert response.status_code == 200
    assert response.json()["can_manage"] is False
    assert (
        entity_client.put("/api/memory/budget/policy", json=_update()).status_code
        == 403
    )
    assert entity_client.get("/api/memory/budget/history").status_code == 403
    assert (
        entity_client.post(
            "/api/memory/budget/rollback",
            json={"expected_version": 0, "target_version": 0},
        ).status_code
        == 403
    )


def test_client_cannot_forge_actor_or_administrator_role(entity_client):
    _login(entity_client, "b")
    payload = _update()
    payload.update(actor_id="D001", role="admin", can_manage=True)
    assert (
        entity_client.put("/api/memory/budget/policy", json=payload).status_code == 422
    )
    assert entity_client.get("/api/memory/budget/policy").json()["version"] == 0


def test_admin_save_conflict_history_and_rollback(entity_client):
    _login(entity_client)
    first = entity_client.put(
        "/api/memory/budget/policy", json=_update(summary_trigger_count=15)
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert first.json()["can_manage"] is True
    assert first.json()["source"] == "persisted"
    assert (
        entity_client.put("/api/memory/budget/policy", json=_update()).status_code
        == 409
    )
    history = entity_client.get("/api/memory/budget/history")
    assert history.status_code == 200
    assert history.json()["versions"][0]["actor_id"] == "D001"
    assert history.json()["versions"][0]["reason"] == "synthetic change"
    rolled = entity_client.post(
        "/api/memory/budget/rollback",
        json={"expected_version": 1, "target_version": 0, "reason": "restore defaults"},
    )
    assert rolled.status_code == 200
    assert rolled.json()["version"] == 2
    assert (
        rolled.json()["policy"]["summary_trigger_count"]
        == BudgetPolicy().summary_trigger_count
    )


@pytest.mark.parametrize("version", [True, 0.0, "0", -1])
def test_expected_version_requires_nonnegative_integer(entity_client, version):
    _login(entity_client)
    assert (
        entity_client.put(
            "/api/memory/budget/policy", json=_update(version)
        ).status_code
        == 422
    )
    assert entity_client.get("/api/memory/budget/policy").json()["version"] == 0


def test_admin_cannot_exceed_server_hard_cap(entity_client):
    _login(entity_client)
    result = entity_client.put(
        "/api/memory/budget/policy", json=_update(context_window=CONTEXT_HARD_MAX + 1)
    )
    assert result.status_code == 422
    current = entity_client.get("/api/memory/budget/policy").json()
    assert current["version"] == 0
    assert current["policy"]["context_window"] <= current["limits"]["context_max"]


def test_revoked_capability_cannot_commit(entity_client, entity_db):
    _login(entity_client)
    assert entity_client.get("/api/memory/budget/policy").json()["can_manage"] is True
    set_budget_admin(
        "D001", False, operator_label="synthetic API revoke", db_path=entity_db
    )
    assert (
        entity_client.put("/api/memory/budget/policy", json=_update()).status_code
        == 403
    )
    assert entity_client.get("/api/memory/budget/policy").json()["version"] == 0


def test_grant_and_revoke_apply_immediately_to_existing_cookie(
    entity_client, entity_db
):
    _login(entity_client, "b")
    assert (
        entity_client.get("/api/auth/me").json()["capabilities"]["budget_admin"]
        is False
    )
    set_budget_admin(
        "D002", True, operator_label="synthetic API grant", db_path=entity_db
    )
    assert (
        entity_client.get("/api/auth/me").json()["capabilities"]["budget_admin"] is True
    )
    assert (
        entity_client.put("/api/memory/budget/policy", json=_update()).status_code
        == 200
    )
    set_budget_admin(
        "D002", False, operator_label="synthetic API revoke", db_path=entity_db
    )
    assert (
        entity_client.get("/api/auth/me").json()["capabilities"]["budget_admin"]
        is False
    )
    assert (
        entity_client.put("/api/memory/budget/policy", json=_update(1)).status_code
        == 403
    )


def test_inactive_admin_cookie_is_rejected(entity_client, entity_db):
    _login(entity_client)
    with transaction(entity_db) as connection:
        UserRepository(connection).deactivate("D001")
    assert entity_client.get("/api/auth/me").status_code == 401
    assert (
        entity_client.put("/api/memory/budget/policy", json=_update()).status_code
        == 401
    )


def test_trace_endpoint_checks_thread_ownership_even_for_admin(
    entity_client, entity_db
):
    own = ThreadService(entity_db).create_thread("D001", "C001")
    foreign = ThreadService(entity_db).create_thread("D002", "C003")
    service = PolicyService(db_path=entity_db)
    own_trace = {"request_id": "synthetic-a", "policy_version": 0, "input_tokens": 101}
    foreign_trace = {
        "request_id": "synthetic-b",
        "policy_version": 0,
        "input_tokens": 202,
    }
    service.record_trace(authorize_scope("D001", own, entity_db), own_trace)
    service.record_trace(authorize_scope("D002", foreign, entity_db), foreign_trace)
    _login(entity_client)
    assert entity_client.get(
        "/api/memory/budget/trace", params={"thread_id": own}
    ).json() == {"trace": own_trace}
    rejected = entity_client.get(
        "/api/memory/budget/trace", params={"thread_id": foreign}
    )
    assert rejected.status_code == 403
    assert "synthetic-b" not in rejected.text
    _login(entity_client, "b")
    assert entity_client.get(
        "/api/memory/budget/trace", params={"thread_id": foreign}
    ).json() == {"trace": foreign_trace}
    assert (
        entity_client.get(
            "/api/memory/budget/trace", params={"thread_id": own}
        ).status_code
        == 403
    )


def test_unavailable_store_never_returns_false_save_success(entity_client, monkeypatch):
    _login(entity_client)

    def unavailable(self):
        raise OSError("synthetic-private-database-location")

    monkeypatch.setattr(PolicyService, "_store", unavailable)
    result = entity_client.put("/api/memory/budget/policy", json=_update())
    assert result.status_code == 503
    assert "synthetic-private-database-location" not in result.text
    current = entity_client.get("/api/memory/budget/policy").json()
    assert current["source"] == "safe_default"
    assert current["policy"]["context_window"] <= CONTEXT_HARD_MAX
