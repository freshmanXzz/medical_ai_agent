"""Authorized memory access; app.sqlite remains the source of facts."""

import logging
from pathlib import Path
from typing import Any

from martin.db import transaction
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.users import UserRepository
from martin.services.access_service import AccessService, EntityNotFoundError

from .namespaces import (
    case_memory_ns,
    doctor_patient_private_ns,
    doctor_preferences_ns,
    patient_memory_ns,
)
from .context import MemorySnapshot
from .store import get_default_store

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, db_path: str | Path | None = None, store=None):
        self.db_path = db_path
        self.store = store

    def _store(self):
        return self.store if self.store is not None else get_default_store()

    def _doctor(self, doctor_id: str) -> None:
        with transaction(self.db_path) as connection:
            doctor = UserRepository(connection).get_by_id(doctor_id)
            if doctor is None or not doctor["is_active"]:
                raise EntityNotFoundError("Active doctor not found")

    def save_doctor_preference(
        self, doctor_id: str, key: str, value: dict[str, Any]
    ) -> None:
        self._doctor(doctor_id)
        self._store().put(doctor_preferences_ns(doctor_id), key, value)

    def get_doctor_preferences(self, doctor_id: str) -> dict[str, dict]:
        self._doctor(doctor_id)
        return {
            item.key: item.value
            for item in self._store().search(
                doctor_preferences_ns(doctor_id), limit=100
            )
        }

    def save_private_patient_note(
        self, doctor_id: str, patient_id: str, key: str, value: dict[str, Any]
    ) -> None:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_patient_authorized(
                doctor_id, patient_id, write=True
            )
            self._store().put(
                doctor_patient_private_ns(doctor_id, patient_id), key, value
            )

    def get_private_patient_notes(
        self, doctor_id: str, patient_id: str
    ) -> dict[str, dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_patient_authorized(doctor_id, patient_id)
            return {
                item.key: item.value
                for item in self._store().search(
                    doctor_patient_private_ns(doctor_id, patient_id), limit=100
                )
            }

    def save_case_memory(
        self, doctor_id: str, case_id: str, key: str, value: dict[str, Any]
    ) -> None:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(
                doctor_id, case_id, write=True
            )
            self._store().put(case_memory_ns(case_id), key, value)

    def get_case_memories(self, doctor_id: str, case_id: str) -> dict[str, dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_case_authorized(doctor_id, case_id)
            return {
                item.key: item.value
                for item in self._store().search(case_memory_ns(case_id), limit=100)
            }

    def sync_finding(self, doctor_id: str, finding_id: str) -> str:
        """Derive one observation from a confirmed business Finding."""
        with transaction(self.db_path) as connection:
            finding = FindingRepository(connection).get_by_id(finding_id)
            if finding is None:
                raise EntityNotFoundError("Finding not found")
            case = AccessService(connection).get_case_authorized(
                doctor_id, finding["case_id"]
            )
            if finding["status"] != "confirmed":
                raise ValueError("Only confirmed findings can enter patient memory")
            key = f"observation:{finding_id}"
            self._store().put(
                patient_memory_ns(case["patient_id"]),
                key,
                {
                    "finding_id": finding_id,
                    "source_case_id": finding["case_id"],
                    "finding_type": finding["finding_type"],
                    "anatomy": finding["anatomy"],
                    "diameter_mm": finding["diameter_mm"],
                    "observed_at": finding["observed_at"],
                    "status": finding["status"],
                },
            )
            return key

    @staticmethod
    def _finding_value(finding) -> dict:
        return {
            "finding_id": finding["id"],
            "source_case_id": finding["case_id"],
            "finding_type": finding["finding_type"],
            "anatomy": finding["anatomy"],
            "diameter_mm": finding["diameter_mm"],
            "observed_at": finding["observed_at"],
            "status": finding["status"],
        }

    def _reconcile_observations(self, connection, patient_id: str, store) -> list[dict]:
        """Rebuild Store from confirmed business facts and remove stale keys."""
        namespace = patient_memory_ns(patient_id)
        facts = {
            row["id"]: row
            for row in FindingRepository(connection).list_by_patient(patient_id)
            if row["status"] == "confirmed"
        }
        for item in store.search(namespace, limit=1000):
            if item.key.startswith("observation:") and item.key[12:] not in facts:
                store.delete(namespace, item.key)
        for finding_id, finding in facts.items():
            store.put(
                namespace,
                f"observation:{finding_id}",
                self._finding_value(finding),
            )
        return sorted(
            [self._finding_value(row) for row in facts.values()],
            key=lambda item: (item["observed_at"], item["finding_id"]),
        )

    def get_patient_observations(
        self, doctor_id: str, patient_id: str
    ) -> list[dict]:
        with transaction(self.db_path) as connection:
            AccessService(connection).get_patient_authorized(doctor_id, patient_id)
            return self._reconcile_observations(connection, patient_id, self._store())

    def snapshot_for_thread(self, doctor_id: str, thread_id: str) -> MemorySnapshot:
        """Resolve business coordinates first; degrade on Store faults."""
        with transaction(self.db_path) as connection:
            thread = AccessService(connection).get_thread_authorized(
                doctor_id, thread_id
            )
            case = CaseRepository(connection).get_by_id(thread["case_id"])
            patient_id = case["patient_id"]
            current = [
                self._finding_value(row)
                for row in FindingRepository(connection).list_by_case(case["id"])
                if row["status"] == "confirmed"
            ]
            basic = {"case_id": case["id"], "patient_id": patient_id,
                     "current_findings": current}
            try:
                store = self._store()
                observations = self._reconcile_observations(
                    connection, patient_id, store
                )
                preferences = {
                    item.key: item.value
                    for item in store.search(
                        doctor_preferences_ns(doctor_id), limit=100
                    )
                }
                notes = {
                    item.key: item.value
                    for item in store.search(
                        doctor_patient_private_ns(doctor_id, patient_id), limit=100
                    )
                }
                case_memories = {
                    item.key: item.value
                    for item in store.search(case_memory_ns(case["id"]), limit=100)
                }
            except Exception:
                logger.warning("跨会话记忆读取失败；当前病例事实仍可使用", exc_info=True)
                return MemorySnapshot(
                    **basic, available=False, error_code="store_unavailable",
                    warning="Long-term memory is temporarily unavailable.",
                )
            return MemorySnapshot(
                **basic,
                doctor_preferences=preferences,
                private_notes=notes,
                historical_observations=[
                    item
                    for item in observations
                    if item["source_case_id"] != case["id"]
                ],
                case_memories=case_memories,
            )
