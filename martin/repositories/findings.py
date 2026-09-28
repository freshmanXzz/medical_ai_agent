"""Medical finding facts; separate IDs preserve longitudinal observations."""

from .base import Repository, new_id, now_utc


class FindingRepository(Repository):
    def create(
        self,
        case_id: str,
        finding_type: str,
        observed_at: str,
        *,
        source_attachment_id: str | None = None,
        created_by: str | None = None,
        anatomy: str | None = None,
        diameter_mm: float | None = None,
        status: str = "confirmed",
        payload_json: str | None = None,
        finding_id: str | None = None,
    ) -> str:
        finding_id = finding_id or new_id()
        now = now_utc()
        self.connection.execute(
            """INSERT INTO findings
               (id, case_id, source_attachment_id, created_by, finding_type,
                anatomy, diameter_mm, observed_at, status, payload_json,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finding_id,
                case_id,
                source_attachment_id,
                created_by,
                finding_type,
                anatomy,
                diameter_mm,
                observed_at,
                status,
                payload_json,
                now,
                now,
            ),
        )
        return finding_id

    def get_by_id(self, finding_id: str):
        return self.connection.execute(
            "SELECT * FROM findings WHERE id = ?", (finding_id,)
        ).fetchone()

    def list_by_case(self, case_id: str):
        return self.connection.execute(
            """SELECT * FROM findings WHERE case_id = ?
               ORDER BY observed_at, id""",
            (case_id,),
        ).fetchall()

    def list_by_patient(self, patient_id: str):
        return self.connection.execute(
            """SELECT findings.* FROM findings
               JOIN cases ON cases.id = findings.case_id
               WHERE cases.patient_id = ? ORDER BY findings.observed_at, findings.id""",
            (patient_id,),
        ).fetchall()
