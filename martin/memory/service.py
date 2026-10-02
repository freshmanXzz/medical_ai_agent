"""Authorized memory access; app.sqlite remains the source of facts."""

import logging
from pathlib import Path
from typing import Any

from martin.db import transaction
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.users import UserRepository
from martin.repositories.threads import ThreadRepository
from martin.services.access_service import AccessService, EntityNotFoundError

from .namespaces import (
    case_memory_ns,
    doctor_patient_private_ns,
    doctor_preferences_ns,
    patient_memory_ns,
    doctor_records_ns,
    records_ns,
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

    def validate_record_source(self, scope, record: dict) -> bool:
        """Reject orphaned, forged and foreign source coordinates on every read."""
        from .scope import revalidate_scope
        from .models import MEMORY_TYPES, normalize_time

        revalidate_scope(scope, db_path=self.db_path)
        if not isinstance(record, dict) or (
            record.get("doctor_id") != scope.doctor_id
            or not isinstance(record.get("memory_type"), str)
            or record.get("memory_type") not in MEMORY_TYPES
            or not isinstance(record.get("memory_id"), str)
            or not record.get("memory_id")
            or record.get("status") not in ("active", "superseded")
        ):
            return False
        global_record = record.get("patient_id") is None
        if global_record:
            if (
                record.get("memory_type") not in (
                    "doctor_preference", "workflow_preference"
                )
                or record.get("case_id") is not None
                or record.get("thread_id") is not None
            ):
                return False
        elif record.get("patient_id") != scope.patient_id:
            return False
        try:
            if any(
                not isinstance(record.get(key), str) or not record[key].strip()
                for key in ("created_at", "observed_at", "source_type", "source_id")
            ):
                return False
            if any(
                record.get(key) is not None and not isinstance(record[key], str)
                for key in ("patient_id", "case_id", "thread_id")
            ):
                return False
            normalize_time(record["created_at"])
            normalize_time(record["observed_at"])
            confidence = record["confidence"]
            if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
                return False
        except (ValueError, TypeError, KeyError):
            return False
        with transaction(self.db_path) as connection:
            case_id, thread_id = record.get("case_id"), record.get("thread_id")
            if case_id is not None:
                case = CaseRepository(connection).get_by_id(case_id)
                if case is None or case["patient_id"] != scope.patient_id:
                    return False
            if thread_id is not None:
                thread = ThreadRepository(connection).get_by_id(thread_id)
                if thread is None or thread["doctor_id"] != scope.doctor_id or (
                    thread["case_id"] != case_id
                ):
                    return False
            source_type, source_id = record.get("source_type"), record.get("source_id")
            if source_type == "doctor":
                return global_record and source_id == scope.doctor_id
            if source_type == "thread":
                return thread_id is not None and source_id == thread_id
            if source_type == "case":
                return case_id is not None and source_id == case_id
            if source_type == "patient":
                return source_id == scope.patient_id and not global_record
            if source_type == "finding":
                finding = FindingRepository(connection).get_by_id(source_id)
                return finding is not None and finding["status"] == "confirmed" and (
                    finding["case_id"] == case_id
                )
            return False

    def list_records(self, scope, *, include_inactive: bool = False) -> list[dict]:
        from .scope import revalidate_scope

        revalidate_scope(scope, db_path=self.db_path)
        store = self._store()
        records = []
        for namespace in (
            doctor_records_ns(scope.doctor_id),
            records_ns(scope.doctor_id, scope.patient_id),
        ):
            offset = 0
            while True:
                page = store.search(namespace, limit=100, offset=offset)
                for item in page:
                    record = item.value
                    if not isinstance(record, dict):
                        continue
                    if (
                        item.key == record.get("memory_id")
                        and (include_inactive or record.get("status") == "active")
                        and self.validate_record_source(scope, record)
                    ):
                        from .models import normalize_time
                        records.append(dict(
                            record,
                            created_at=normalize_time(record["created_at"]),
                            observed_at=normalize_time(record["observed_at"]),
                        ))
                if len(page) < 100:
                    break
                offset += len(page)
        revalidate_scope(scope, db_path=self.db_path)
        return sorted(
            records,
            key=lambda record: (record["observed_at"], record["memory_id"]),
        )

    def get_record(self, scope, memory_id: str) -> dict | None:
        from .scope import revalidate_scope

        revalidate_scope(scope, db_path=self.db_path)
        for namespace in (
            records_ns(scope.doctor_id, scope.patient_id),
            doctor_records_ns(scope.doctor_id),
        ):
            item = self._store().get(namespace, memory_id)
            if (
                item and isinstance(item.value, dict)
                and item.value.get("memory_id") == memory_id
                and item.value.get("status") == "active"
                and self.validate_record_source(scope, item.value)
            ):
                return dict(item.value)
        return None

    def _doctor(self, doctor_id: str) -> None:
        with transaction(self.db_path) as connection:
            doctor = UserRepository(connection).get_by_id(doctor_id)
            if doctor is None or not doctor["is_active"]:
                raise EntityNotFoundError("Active doctor not found")

    def save_doctor_preference(
        self, doctor_id: str, key: str, value: dict[str, Any]
    ) -> None:
        self._doctor(doctor_id)
        from types import SimpleNamespace
        from langgraph.store.base import PutOp
        from .models import MemoryCandidate, new_record

        scope = SimpleNamespace(
            doctor_id=doctor_id, patient_id=None, case_id=None, thread_id=None,
        )
        candidate = MemoryCandidate("doctor_preference", logical_key=key, data=value)
        record = new_record(
            scope, candidate, source_type="doctor", source_id=doctor_id,
        )
        record["memory_id"] = "preference:" + key
        # Preserve the V1 key/value contract, and persist typed provenance atomically.
        self._store().batch([
            PutOp(namespace=doctor_preferences_ns(doctor_id), key=key, value=value),
            PutOp(
                namespace=doctor_records_ns(doctor_id),
                key=record["memory_id"], value=record,
            ),
        ])

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
                    and self._is_prior_observation(item, current)
                ],
                case_memories=case_memories,
            )

    @staticmethod
    def _is_prior_observation(observation: dict, current: list[dict]) -> bool:
        from .models import normalize_time

        try:
            observed = normalize_time(observation["observed_at"])
            anchor = max(normalize_time(item["observed_at"]) for item in current)
        except (ValueError, TypeError, KeyError):
            return False
        return observed <= anchor
