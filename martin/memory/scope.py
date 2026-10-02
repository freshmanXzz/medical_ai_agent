"""Resolve memory coordinates from current business authorization."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from martin.db import transaction
from martin.repositories.users import UserRepository
from martin.services.access_service import (
    AccessDeniedError,
    AccessService,
    EntityNotFoundError,
)


@dataclass(frozen=True)
class MemoryScope:
    doctor_id: str
    patient_id: str
    case_id: str
    thread_id: str


def _authorize_scope_on_connection(
    connection: sqlite3.Connection,
    doctor_id: str,
    thread_id: str,
    *,
    patient_id: str | None = None,
    case_id: str | None = None,
    write: bool = False,
) -> MemoryScope:
    """Check authorization in the same transaction as a fact retrieval."""
    for value in (doctor_id, thread_id, patient_id, case_id):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("Memory scope requires non-empty entity IDs")
    doctor = UserRepository(connection).get_by_id(doctor_id)
    if doctor is None or not doctor["is_active"] or doctor["role"] != "doctor":
        raise EntityNotFoundError("Active doctor not found")
    access = AccessService(connection)
    thread = access.get_thread_authorized(doctor_id, thread_id, write=write)
    case = access.get_case_authorized(doctor_id, thread["case_id"], write=write)
    if case_id is not None and case_id != case["id"]:
        raise AccessDeniedError("Memory case does not match thread")
    if patient_id is not None and patient_id != case["patient_id"]:
        raise AccessDeniedError("Memory patient does not match thread")
    return MemoryScope(doctor_id, case["patient_id"], case["id"], thread_id)


def authorize_scope(
    doctor_id: str,
    thread_id: str,
    db_path: str | Path | None = None,
    *,
    patient_id: str | None = None,
    case_id: str | None = None,
    write: bool = False,
) -> MemoryScope:
    """Identity and coordinates come from the business DB, never a prompt."""
    with transaction(db_path) as connection:
        connection.execute("BEGIN")
        return _authorize_scope_on_connection(
            connection,
            doctor_id,
            thread_id,
            patient_id=patient_id,
            case_id=case_id,
            write=write,
        )


def revalidate_scope(
    scope: MemoryScope,
    db_path: str | Path | None = None,
    *,
    write: bool = False,
) -> MemoryScope:
    """A previously resolved or caller-created scope is not an access grant."""
    return authorize_scope(
        scope.doctor_id,
        scope.thread_id,
        db_path,
        patient_id=scope.patient_id,
        case_id=scope.case_id,
        write=write,
    )
