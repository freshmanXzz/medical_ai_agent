"""Business thread persistence; checkpoint lifecycle belongs to services."""

from .base import Repository, new_id, now_utc


class ThreadRepository(Repository):
    def create(
        self,
        doctor_id: str,
        case_id: str,
        *,
        thread_id: str | None = None,
    ) -> str:
        thread_id = thread_id or new_id()
        now = now_utc()
        self.connection.execute(
            """INSERT INTO threads
               (id, doctor_id, case_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (thread_id, doctor_id, case_id, now, now),
        )
        return thread_id

    def get_by_id(self, thread_id: str):
        return self.connection.execute(
            "SELECT * FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()

    def list_by_case(self, case_id: str):
        return self.connection.execute(
            "SELECT * FROM threads WHERE case_id = ? ORDER BY created_at, id",
            (case_id,),
        ).fetchall()

    def list_by_doctor(self, doctor_id: str):
        return self.connection.execute(
            "SELECT * FROM threads WHERE doctor_id = ? ORDER BY created_at, id",
            (doctor_id,),
        ).fetchall()

    def delete(self, thread_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM threads WHERE id = ?", (thread_id,)
        )
        return cursor.rowcount == 1
