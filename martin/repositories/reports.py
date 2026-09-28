"""Versioned report fact persistence."""

from .base import Repository, new_id, now_utc


class ReportRepository(Repository):
    def create_version(
        self,
        case_id: str,
        content: str,
        *,
        created_by: str | None = None,
        status: str = "draft",
        version: int | None = None,
        report_id: str | None = None,
    ) -> str:
        if version is None:
            version = self.connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM reports WHERE case_id = ?",
                (case_id,),
            ).fetchone()[0]
        report_id = report_id or new_id()
        self.connection.execute(
            """INSERT INTO reports
               (id, case_id, created_by, version, status, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (report_id, case_id, created_by, version, status, content, now_utc()),
        )
        return report_id

    def list_by_case(self, case_id: str):
        return self.connection.execute(
            "SELECT * FROM reports WHERE case_id = ? ORDER BY version",
            (case_id,),
        ).fetchall()

    def get_latest(self, case_id: str):
        return self.connection.execute(
            """SELECT * FROM reports WHERE case_id = ?
               ORDER BY version DESC LIMIT 1""",
            (case_id,),
        ).fetchone()
