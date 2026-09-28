"""Case attachment metadata persistence."""

from .base import Repository, new_id, now_utc


class AttachmentRepository(Repository):
    def create(
        self,
        case_id: str,
        original_name: str,
        storage_path: str,
        *,
        uploaded_by: str | None = None,
        mime_type: str | None = None,
        sha256: str | None = None,
        attachment_id: str | None = None,
    ) -> str:
        attachment_id = attachment_id or new_id()
        self.connection.execute(
            """INSERT INTO attachments
               (id, case_id, uploaded_by, original_name, storage_path,
                mime_type, sha256, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attachment_id,
                case_id,
                uploaded_by,
                original_name,
                storage_path,
                mime_type,
                sha256,
                now_utc(),
            ),
        )
        return attachment_id

    def get_by_id(self, attachment_id: str):
        return self.connection.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()

    def get_by_storage_path(self, case_id: str, storage_path: str):
        return self.connection.execute(
            """SELECT * FROM attachments
               WHERE case_id = ? AND storage_path = ?""",
            (case_id, storage_path),
        ).fetchone()

    def mark_analyzed(self, attachment_id: str, analyzed_at: str) -> bool:
        cursor = self.connection.execute(
            "UPDATE attachments SET analyzed_at = ? WHERE id = ?",
            (analyzed_at, attachment_id),
        )
        return cursor.rowcount == 1

    def list_by_case(self, case_id: str):
        return self.connection.execute(
            "SELECT * FROM attachments WHERE case_id = ? ORDER BY created_at, id",
            (case_id,),
        ).fetchall()

    def delete(self, attachment_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM attachments WHERE id = ?", (attachment_id,)
        )
        return cursor.rowcount == 1
