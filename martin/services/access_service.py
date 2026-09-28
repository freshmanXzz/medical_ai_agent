"""Doctor access checks against business facts, never checkpoint contents."""

import sqlite3

from martin.repositories.access import AccessRepository
from martin.repositories.cases import CaseRepository
from martin.repositories.patients import PatientRepository
from martin.repositories.threads import ThreadRepository


class EntityNotFoundError(Exception):
    pass


class AccessDeniedError(Exception):
    pass


class AccessService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get_patient_authorized(
        self, doctor_id: str, patient_id: str, *, write: bool = False
    ) -> dict:
        patient = PatientRepository(self.connection).get_by_id(patient_id)
        if patient is None:
            raise EntityNotFoundError("Patient not found")
        grant = AccessRepository(self.connection).get_access(doctor_id, patient_id)
        if grant is None or (write and grant["access_level"] != "read_write"):
            raise AccessDeniedError("Patient access denied")
        return dict(patient)

    def get_case_authorized(
        self, doctor_id: str, case_id: str, *, write: bool = False
    ) -> dict:
        case = CaseRepository(self.connection).get_by_id(case_id)
        if case is None:
            raise EntityNotFoundError("Case not found")
        self.get_patient_authorized(doctor_id, case["patient_id"], write=write)
        return dict(case)

    def get_thread_authorized(
        self, doctor_id: str, thread_id: str, *, write: bool = False
    ) -> dict:
        thread = ThreadRepository(self.connection).get_by_id(thread_id)
        if thread is None:
            raise EntityNotFoundError("Thread not found")
        if thread["doctor_id"] != doctor_id:
            raise AccessDeniedError("Thread access denied")
        self.get_case_authorized(doctor_id, thread["case_id"], write=write)
        return dict(thread)
