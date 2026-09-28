"""Actor-scoped patient and case reads."""

from pathlib import Path

from martin.db import transaction
from martin.repositories.cases import CaseRepository

from .access_service import AccessService


class CaseService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def get_patient_authorized(self, doctor_id: str, patient_id: str) -> dict:
        with transaction(self.db_path) as connection:
            return AccessService(connection).get_patient_authorized(doctor_id, patient_id)

    def get_case_authorized(self, doctor_id: str, case_id: str) -> dict:
        with transaction(self.db_path) as connection:
            return AccessService(connection).get_case_authorized(doctor_id, case_id)

    def list_cases_for_patient_authorized(self, doctor_id: str, patient_id: str) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_patient_authorized(doctor_id, patient_id)
            return [dict(row) for row in CaseRepository(connection).list_by_patient(patient_id)]
