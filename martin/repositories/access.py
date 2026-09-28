"""Doctor-patient access relationship persistence, without policy decisions."""

from .base import Repository, now_utc


class AccessRepository(Repository):
    def grant(
        self,
        doctor_id: str,
        patient_id: str,
        *,
        access_level: str = "read_write",
    ) -> None:
        self.connection.execute(
            """INSERT INTO doctor_patient_access
               (doctor_id, patient_id, access_level, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(doctor_id, patient_id)
               DO UPDATE SET access_level = excluded.access_level""",
            (doctor_id, patient_id, access_level, now_utc()),
        )

    def revoke(self, doctor_id: str, patient_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM doctor_patient_access WHERE doctor_id = ? AND patient_id = ?",
            (doctor_id, patient_id),
        )
        return cursor.rowcount == 1

    def get_access(self, doctor_id: str, patient_id: str):
        return self.connection.execute(
            """SELECT * FROM doctor_patient_access
               WHERE doctor_id = ? AND patient_id = ?""",
            (doctor_id, patient_id),
        ).fetchone()
