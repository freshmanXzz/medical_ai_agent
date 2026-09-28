"""Patient persistence; callers must enforce doctor access."""

from .base import Repository, new_id, now_utc


class PatientRepository(Repository):
    def create(
        self,
        name: str,
        *,
        sex: str | None = None,
        birth_date: str | None = None,
        patient_id: str | None = None,
    ) -> str:
        patient_id = patient_id or new_id()
        now = now_utc()
        self.connection.execute(
            """INSERT INTO patients
               (id, name, sex, birth_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (patient_id, name, sex, birth_date, now, now),
        )
        return patient_id

    def get_by_id(self, patient_id: str):
        return self.connection.execute(
            "SELECT * FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()

    def update_sex(self, patient_id: str, sex: str) -> bool:
        cursor = self.connection.execute(
            "UPDATE patients SET sex = ?, updated_at = ? WHERE id = ?",
            (sex, now_utc(), patient_id),
        )
        return cursor.rowcount == 1

    def delete(self, patient_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM patients WHERE id = ?", (patient_id,)
        )
        return cursor.rowcount == 1
