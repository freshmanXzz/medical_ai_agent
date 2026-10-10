"""Read compatibility and lifecycle rules shared by every memory projection."""

import threading
from copy import deepcopy
from datetime import datetime, timezone

from .models import normalize_time

MEMORY_STATUSES = frozenset({"active", "superseded", "retracted", "invalid"})
PROVENANCE_KINDS = frozenset(
    {"message", "api_submission", "business_event", "legacy_unknown"}
)
write_lock = threading.RLock()


def atomic_batch(store, operations):
    """Commit lifecycle PutOps together, including projection deletion.

    The installed SqliteStore cursor commits in ``finally`` even if one of its
    statements fails. Its public batch therefore cannot provide this contract.
    Reuse its SQL builder under the same connection lock with explicit rollback.
    Custom store/batch implementations retain their own public batch contract.
    """
    from langgraph.store.base import PutOp
    from langgraph.store.sqlite import SqliteStore

    operations = list(operations)
    if any(not isinstance(operation, PutOp) for operation in operations):
        raise ValueError("Lifecycle batches only support PutOps")
    if (
        not isinstance(store, SqliteStore)
        or getattr(store.batch, "__func__", None) is not SqliteStore.batch
    ):
        return store.batch(operations)
    if not store.is_setup:
        store.setup()
    with store.lock:
        store.conn.execute("BEGIN")
        cursor = store.conn.cursor()
        try:
            store._batch_put_ops(list(enumerate(operations)), cursor)
            store.conn.execute("COMMIT")
        except BaseException:
            if store.conn.in_transaction:
                store.conn.execute("ROLLBACK")
            raise
        finally:
            cursor.close()
    return [None] * len(operations)


def normalize_provenance(provenance=None, *, doctor_id=None) -> dict:
    """Preserve supplied source coordinates; never invent a message reference."""
    if provenance is None:
        return {
            "kind": "legacy_unknown",
            "actor_id": doctor_id,
            "actor_role": "doctor",
            "message_id": None,
            "submission_id": None,
            "thread_id": None,
        }
    if not isinstance(provenance, dict):
        raise ValueError("Memory provenance must be an object")
    if set(provenance) - {
        "kind",
        "actor_id",
        "actor_role",
        "message_id",
        "submission_id",
        "thread_id",
    }:
        raise ValueError("Unsupported memory provenance field")
    result = deepcopy(provenance)
    if result.get("kind") not in PROVENANCE_KINDS:
        raise ValueError("Unknown memory provenance kind")
    for name in ("actor_id", "actor_role", "message_id", "submission_id", "thread_id"):
        result.setdefault(name, None)
        value = result[name]
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > 200
        ):
            raise ValueError("Invalid memory provenance coordinate")
    if result["actor_role"] not in (None, "doctor"):
        raise ValueError("Only doctor evidence may enter authored memory")
    if doctor_id is not None and result["actor_id"] not in (None, doctor_id):
        raise ValueError(
            "Memory provenance actor differs from the authenticated doctor"
        )
    if result["kind"] != "legacy_unknown":
        if not result["actor_id"] or result["actor_role"] != "doctor":
            raise ValueError("Memory provenance requires the authenticated doctor")
        if doctor_id is not None and result["actor_id"] != doctor_id:
            raise ValueError(
                "Memory provenance actor differs from the authenticated doctor"
            )
    if result["kind"] == "message" and (
        not result["message_id"] or not result["thread_id"]
    ):
        raise ValueError("Message provenance requires a real message and thread")
    if result["kind"] == "api_submission" and (
        not result["submission_id"] or result["message_id"] is not None
    ):
        raise ValueError(
            "API provenance requires a submission ID and cannot claim a message"
        )
    if result["kind"] != "message" and result["message_id"] is not None:
        raise ValueError("Only message provenance may identify a source message")
    if result["kind"] != "api_submission" and result["submission_id"] is not None:
        raise ValueError("Only API provenance may identify a submission")
    return result


def normalize_record(record: dict) -> dict:
    """Adapt old rows in memory, without rewriting their original coordinates."""
    result = deepcopy(record)
    result.setdefault("schema_version", 1)
    result.setdefault("status", "active")
    result.setdefault(
        "provenance", normalize_provenance(doctor_id=result.get("doctor_id"))
    )
    result.setdefault(
        "source_message_id",
        (
            result["provenance"].get("message_id")
            if isinstance(result["provenance"], dict)
            else None
        ),
    )
    return result


def is_record_active(record: dict, now=None) -> bool:
    if record.get("status", "active") != "active":
        return False
    valid_until = record.get("valid_until")
    if valid_until is None:
        return True
    try:
        expiry = normalize_time(valid_until)
        instant = now.isoformat() if isinstance(now, datetime) else now
        return expiry > normalize_time(instant)
    except (ValueError, TypeError):
        return False


def lifecycle_event(
    action, target_id, doctor_id, *, reason="", provenance=None
) -> dict:
    if not isinstance(reason, str) or len(reason) > 500:
        raise ValueError("Memory change reason must be a bounded string")
    return {
        "action": action,
        "target_id": target_id,
        "actor_id": doctor_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "provenance": normalize_provenance(provenance, doctor_id=doctor_id),
    }
