"""Create business threads after validating case access."""

from pathlib import Path

from martin.db import transaction
from martin.repositories.threads import ThreadRepository
from martin.repositories.audit import AuditRepository

from .access_service import AccessDeniedError, AccessService, EntityNotFoundError


class ThreadService:
    def __init__(self, db_path: str | Path | None = None, checkpointer=None):
        self.db_path = db_path
        self.checkpointer = checkpointer

    def create_thread(self, doctor_id: str, case_id: str) -> str:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id, write=True)
            return ThreadRepository(connection).create(doctor_id, case_id)

    def get_thread_authorized(
        self, doctor_id: str, thread_id: str, *, write: bool = False
    ) -> dict:
        with transaction(self.db_path) as connection:
            return AccessService(connection).get_thread_authorized(
                doctor_id, thread_id, write=write
            )

    def list_by_case_authorized(self, doctor_id: str, case_id: str) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id)
            return [dict(row) for row in ThreadRepository(connection).list_by_case(case_id)]

    def list_authorized_ids(self, doctor_id: str) -> set[str]:
        with transaction(self.db_path) as connection:
            access = AccessService(connection)
            rows = ThreadRepository(connection).list_by_doctor(doctor_id)
            allowed = set()
            for row in rows:
                try:
                    access.get_thread_authorized(doctor_id, row["id"])
                except (AccessDeniedError, EntityNotFoundError):
                    continue
                allowed.add(row["id"])
            return allowed

    def delete_thread(self, doctor_id: str, thread_id: str) -> None:
        """Delete checkpoint first; retain the business row on saver failure."""
        from martin.agent.sessions import delete_thread_checkpoints

        with transaction(self.db_path) as connection:
            AccessService(connection).get_thread_authorized(
                doctor_id, thread_id, write=True
            )
            delete_thread_checkpoints(thread_id, self.checkpointer)
            if not ThreadRepository(connection).delete(thread_id):
                raise EntityNotFoundError("Thread disappeared during deletion")
            AuditRepository(connection).append(
                "thread", thread_id, "deleted", actor_user_id=doctor_id
            )
