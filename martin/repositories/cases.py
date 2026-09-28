"""Case persistence without authorization decisions."""

from .base import Repository, new_id, now_utc


class CaseRepository(Repository):
    def create(
        self,
        patient_id: str,
        *,
        case_type: str = "general",
        case_id: str | None = None,
    ) -> str:
        case_id = case_id or new_id()
        now = now_utc()
        self.connection.execute(
            """INSERT INTO cases
               (id, patient_id, case_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (case_id, patient_id, case_type, now, now),
        )
        return case_id

    def get_by_id(self, case_id: str):
        return self.connection.execute(
            "SELECT * FROM cases WHERE id = ?", (case_id,)
        ).fetchone()

    def update_clinical_fields(self, case_id: str, changes: dict[str, object]) -> None:
        allowed = {
            "age_at_encounter_years",
            "age_recorded_at",
            "smoking_history",
            "family_history",
            "clinical_notes_json",
        }
        if not changes or not changes.keys() <= allowed:
            raise ValueError("Invalid clinical fields")
        columns = ", ".join(f"{column} = ?" for column in changes)
        self.connection.execute(
            f"UPDATE cases SET {columns}, updated_at = ? WHERE id = ?",
            (*changes.values(), now_utc(), case_id),
        )

    def list_by_patient(self, patient_id: str):
        return self.connection.execute(
            "SELECT * FROM cases WHERE patient_id = ? ORDER BY created_at, id",
            (patient_id,),
        ).fetchall()

    def delete(self, case_id: str) -> bool:
        cursor = self.connection.execute("DELETE FROM cases WHERE id = ?", (case_id,))
        return cursor.rowcount == 1
