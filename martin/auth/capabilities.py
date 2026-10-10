"""Separate budget administration from existing patient access grants.

Capability writes are exposed only by the local maintenance command. A missing
column or unavailable database is fail-closed for the HTTP authorization read.
"""

import json
import sqlite3

from martin.db import transaction
from martin.repositories.audit import AuditRepository
from martin.repositories.base import now_utc
from martin.repositories.users import UserRepository
from martin.services.access_service import EntityNotFoundError


def is_budget_admin(doctor_id, *, db_path=None) -> bool:
    try:
        with transaction(db_path) as connection:
            user = UserRepository(connection).get_by_id(doctor_id)
            return bool(
                user
                and user["is_active"]
                and user["role"] == "doctor"
                and "budget_admin" in user.keys()
                and user["budget_admin"] == 1
            )
    except sqlite3.Error:
        return False


def set_budget_admin(doctor_id, enabled, *, operator_label, db_path=None):
    """Explicit maintenance action; atomic capability and audit, no access grants."""
    if type(enabled) is not bool:
        raise ValueError("Capability value must be boolean")
    if (
        not isinstance(operator_label, str)
        or not operator_label.strip()
        or len(operator_label) > 120
    ):
        raise ValueError("An explicit bounded maintenance operator label is required")
    from martin.memory.lifecycle import write_lock

    with write_lock, transaction(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = UserRepository(connection).get_by_id(doctor_id)
        if not user or not user["is_active"] or user["role"] != "doctor":
            raise EntityNotFoundError("Active doctor not found")
        if "budget_admin" not in user.keys():
            raise ValueError(
                "Initialize the additive database schema before granting capabilities"
            )
        previous = bool(user["budget_admin"])
        if previous == enabled:
            return {"doctor_id": doctor_id, "budget_admin": enabled, "changed": False}
        connection.execute(
            "UPDATE users SET budget_admin=?, updated_at=? WHERE id=?",
            (int(enabled), now_utc(), doctor_id),
        )
        AuditRepository(connection).append(
            "user_capability",
            doctor_id,
            "budget_admin_granted" if enabled else "budget_admin_revoked",
            before_json=json.dumps({"budget_admin": previous}),
            after_json=json.dumps(
                {"budget_admin": enabled, "operator_label": operator_label.strip()}
            ),
        )
        return {"doctor_id": doctor_id, "budget_admin": enabled, "changed": True}
