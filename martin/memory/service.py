"""Authorized memory access; app.sqlite remains the source of facts."""

import logging
from pathlib import Path
from typing import Any

from martin.db import transaction
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.repositories.threads import ThreadRepository
from martin.repositories.users import UserRepository
from martin.services.access_service import AccessService, EntityNotFoundError

from .context import MemorySnapshot
from .lifecycle import (
    MEMORY_STATUSES,
    atomic_batch,
    is_record_active,
    lifecycle_event,
    normalize_provenance,
    normalize_record,
    write_lock,
)
from .namespaces import (
    case_memory_ns,
    doctor_patient_private_ns,
    doctor_preferences_ns,
    doctor_records_ns,
    patient_memory_ns,
    records_ns,
)
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
        from .models import MEMORY_TYPES, normalize_time
        from .scope import revalidate_scope

        revalidate_scope(scope, db_path=self.db_path)
        if not isinstance(record, dict) or (
            record.get("doctor_id") != scope.doctor_id
            or not isinstance(record.get("memory_type"), str)
            or record.get("memory_type") not in MEMORY_TYPES
            or not isinstance(record.get("memory_id"), str)
            or not record.get("memory_id")
            or not isinstance(record.get("logical_key"), str)
            or not record["logical_key"].strip()
            or len(record["logical_key"]) > 120
            or not isinstance(record.get("status"), str)
            or record.get("status") not in MEMORY_STATUSES
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
            provenance = normalize_provenance(
                record.get("provenance"), doctor_id=scope.doctor_id
            )
            if provenance["kind"] == "business_event" and (
                record["memory_type"]
                not in ("patient_fact", "medical_observation", "case_evolution")
                or record.get("source_type") not in ("patient", "finding", "case")
            ):
                return False
            if record.get("source_message_id") != provenance.get("message_id"):
                return False
            if (
                provenance["kind"] == "message"
                and record.get("interaction_id") != provenance["message_id"]
            ):
                return False
            if (
                provenance["kind"] == "api_submission"
                and record.get("interaction_id") is not None
            ):
                return False
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
            if record.get("valid_until") is not None:
                if record["memory_type"] not in (
                    "workflow_preference",
                    "task_followup",
                ):
                    return False
                normalize_time(record["valid_until"])
            confidence = record["confidence"]
            if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
                return False
            from .models import MemoryCandidate

            MemoryCandidate(
                record["memory_type"],
                record.get("text", ""),
                record.get("logical_key"),
                record.get("data", {}),
                valid_until=record.get("valid_until"),
            ).validate()
        except (ValueError, TypeError, KeyError):
            return False
        reinforced = record.get("reinforced_sources", [])
        if not isinstance(reinforced, list):
            return False
        for reference in reinforced:
            if not isinstance(reference, dict):
                return False
            occurrence = dict(record, **reference)
            occurrence.pop("reinforced_sources", None)
            occurrence.pop("deduplication_events", None)
            if not self.validate_record_source(scope, occurrence):
                return False
        with transaction(self.db_path) as connection:
            provenance_thread = provenance.get("thread_id")
            if provenance_thread:
                source_thread = ThreadRepository(connection).get_by_id(
                    provenance_thread
                )
                if (
                    source_thread is None
                    or source_thread["doctor_id"] != scope.doctor_id
                ):
                    return False
                if not global_record and provenance_thread != record.get("thread_id"):
                    return False
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
                    record = normalize_record(record)
                    if (
                        item.key == record.get("memory_id")
                        and (include_inactive or is_record_active(record))
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
        present = {record["memory_id"] for record in records}
        for record in self._all_doctor_records(scope.doctor_id):
            if (
                record["memory_id"] not in present
                and (include_inactive or is_record_active(record))
                and self.validate_record_source(scope, record)
            ):
                records.append(record)
        revalidate_scope(scope, db_path=self.db_path)
        return sorted(
            records,
            key=lambda record: (record["observed_at"], record["memory_id"]),
        )

    def get_record(
        self, scope, memory_id: str, *, include_inactive: bool = False
    ) -> dict | None:
        from .scope import revalidate_scope

        revalidate_scope(scope, db_path=self.db_path)
        for namespace in (
            records_ns(scope.doctor_id, scope.patient_id),
            doctor_records_ns(scope.doctor_id),
        ):
            item = self._store().get(namespace, memory_id)
            record = (
                normalize_record(item.value)
                if item and isinstance(item.value, dict)
                else None
            )
            if (
                record
                and record.get("memory_id") == memory_id
                and (include_inactive or is_record_active(record))
                and self.validate_record_source(scope, record)
            ):
                return record
        for record in self._all_doctor_records(scope.doctor_id):
            if (
                record["memory_id"] == memory_id
                and (include_inactive or is_record_active(record))
                and self.validate_record_source(scope, record)
            ):
                return record
        return None

    def record_history(self, scope, memory_id: str) -> list[dict]:
        target = self.get_record(scope, memory_id, include_inactive=True)
        if target is None:
            raise EntityNotFoundError("Memory not found")
        records = self.list_records(scope, include_inactive=True)
        related = {memory_id}
        while True:
            expanded = related | {
                row["memory_id"]
                for row in records
                if row.get("supersedes") in related
                or row.get("superseded_by") in related
                or row["memory_id"]
                in {
                    linked
                    for item in records
                    if item["memory_id"] in related
                    for linked in (item.get("supersedes"), item.get("superseded_by"))
                }
            }
            if expanded == related:
                break
            related = expanded
        return sorted(
            (row for row in records if row["memory_id"] in related),
            key=lambda row: (row["created_at"], row["memory_id"]),
        )

    def retract_record(
        self, scope, memory_id: str, *, reason="", provenance=None
    ) -> dict:
        from langgraph.store.base import PutOp

        from .scope import revalidate_scope

        revalidate_scope(scope, db_path=self.db_path, write=True)
        event = lifecycle_event(
            "retract", memory_id, scope.doctor_id, reason=reason, provenance=provenance
        )
        if event["provenance"].get("thread_id") not in (None, scope.thread_id):
            raise ValueError("Retraction provenance must identify the current thread")
        with write_lock:
            record = self.get_record(scope, memory_id, include_inactive=True)
            if record is None:
                raise EntityNotFoundError("Memory not found")
            if record["status"] == "retracted":
                return record
            if record["memory_type"] in (
                "patient_fact",
                "medical_observation",
                "case_evolution",
            ):
                raise ValueError("Confirmed facts require the business update service")
            updated = dict(
                record,
                status="retracted",
                retracted_at=event["occurred_at"],
                audit_events=[*record.get("audit_events", []), event],
            )
            namespace = (
                doctor_records_ns(scope.doctor_id)
                if record.get("patient_id") is None
                else records_ns(scope.doctor_id, scope.patient_id)
            )
            operations = [PutOp(namespace=namespace, key=memory_id, value=updated)]
            if (
                record["memory_type"] == "doctor_preference"
                and record["status"] == "active"
            ):
                operations.append(
                    PutOp(
                        namespace=doctor_preferences_ns(scope.doctor_id),
                        key=record["logical_key"],
                        value=None,
                    )
                )
            revalidate_scope(scope, db_path=self.db_path, write=True)
            atomic_batch(self._store(), operations)
            return updated

    def _doctor(self, doctor_id: str) -> None:
        with transaction(self.db_path) as connection:
            doctor = UserRepository(connection).get_by_id(doctor_id)
            if doctor is None or not doctor["is_active"] or doctor["role"] != "doctor":
                raise EntityNotFoundError("Active doctor not found")

    def save_doctor_preference(
        self,
        doctor_id: str,
        key: str,
        value: dict[str, Any],
        *,
        provenance=None,
        reason: str = "",
    ) -> dict:
        self._doctor(doctor_id)
        from types import SimpleNamespace

        from langgraph.store.base import PutOp

        from .models import MemoryCandidate, new_record

        scope = SimpleNamespace(
            doctor_id=doctor_id, patient_id=None, case_id=None, thread_id=None,
        )
        candidate = MemoryCandidate("doctor_preference", logical_key=key, data=value)
        record = new_record(
            scope,
            candidate,
            source_type="doctor",
            source_id=doctor_id,
            provenance=provenance,
        )
        record["interaction_id"] = record["provenance"].get("message_id")
        if not self._valid_doctor_record(doctor_id, record):
            raise ValueError("Preference source is outside the authenticated doctor")
        lifecycle_event(
            "write",
            record["memory_id"],
            doctor_id,
            reason=reason,
            provenance=provenance,
        )
        with write_lock:
            previous = [
                row
                for row in self._all_doctor_records(doctor_id)
                if row.get("memory_type") == "doctor_preference"
                and row.get("logical_key") == key
            ]
            active = [
                row
                for row in previous
                if is_record_active(row) and self._valid_doctor_record(doctor_id, row)
            ]
            if len(active) == 1 and active[0].get("data") == value:
                return active[0]
            record["revision"] = (
                max((row.get("revision", 1) for row in previous), default=0) + 1
            )
            operations = []
            for prior in active:
                event = lifecycle_event(
                    "supersede",
                    prior["memory_id"],
                    doctor_id,
                    reason=reason,
                    provenance=provenance,
                )
                old = dict(
                    prior,
                    status="superseded",
                    superseded_by=record["memory_id"],
                    audit_events=[*prior.get("audit_events", []), event],
                )
                operations.append(
                    PutOp(
                        namespace=doctor_records_ns(doctor_id),
                        key=old["memory_id"],
                        value=old,
                    )
                )
                record["supersedes"] = old["memory_id"]
            if not active and previous:
                record["supersedes"] = max(
                    previous,
                    key=lambda row: (row.get("revision", 1), row["created_at"]),
                )["memory_id"]
            operations.extend(
                [
                    PutOp(
                        namespace=doctor_preferences_ns(doctor_id), key=key, value=value
                    ),
                    PutOp(
                        namespace=doctor_records_ns(doctor_id),
                        key=record["memory_id"],
                        value=record,
                    ),
                ]
            )
            self._doctor(doctor_id)
            atomic_batch(self._store(), operations)
            return record

    def _valid_doctor_record(self, doctor_id: str, record: dict) -> bool:
        """Validate a doctor-wide source even when no case/thread is selected."""
        from .models import MemoryCandidate, normalize_time

        try:
            if (
                record.get("doctor_id") != doctor_id
                or record.get("memory_type")
                not in ("doctor_preference", "workflow_preference")
                or any(
                    record.get(key) is not None
                    for key in ("patient_id", "case_id", "thread_id")
                )
                or record.get("source_type") != "doctor"
                or record.get("source_id") != doctor_id
                or record.get("status") not in MEMORY_STATUSES
                or not isinstance(record.get("memory_id"), str)
                or not record["memory_id"]
                or any(
                    not isinstance(record.get(key), str) or not record[key].strip()
                    for key in ("created_at", "observed_at", "logical_key")
                )
            ):
                return False
            MemoryCandidate(
                record["memory_type"],
                record.get("text", ""),
                record["logical_key"],
                record["data"],
                confidence=record["confidence"],
                valid_until=record.get("valid_until"),
            ).validate()
            normalize_time(record["created_at"])
            normalize_time(record["observed_at"])
            source = normalize_provenance(record.get("provenance"), doctor_id=doctor_id)
            if source["kind"] == "business_event":
                return False
            if record.get("source_message_id") != source.get("message_id"):
                return False
            if (
                source["kind"] == "message"
                and record.get("interaction_id") != source["message_id"]
            ):
                return False
            if (
                source["kind"] == "api_submission"
                and record.get("interaction_id") is not None
            ):
                return False
            if source.get("thread_id"):
                with transaction(self.db_path) as connection:
                    thread = ThreadRepository(connection).get_by_id(source["thread_id"])
                    if thread is None or thread["doctor_id"] != doctor_id:
                        return False
            return True
        except (ValueError, TypeError, KeyError):
            return False

    def _all_doctor_records(self, doctor_id: str) -> list[dict]:
        result, offset = [], 0
        known_keys = set()
        unidentified_preference_history = False
        while True:
            page = self._store().search(
                doctor_records_ns(doctor_id), limit=100, offset=offset
            )
            for item in page:
                row = item.value
                if (
                    not isinstance(row, dict)
                    or row.get("memory_type") != "doctor_preference"
                ):
                    continue
                key = row.get("logical_key")
                if isinstance(key, str) and key.strip() and len(key) <= 120:
                    known_keys.add(key)
                if (
                    not isinstance(key, str)
                    or not key.strip()
                    or len(key) > 120
                    or item.key != row.get("memory_id")
                    or row.get("doctor_id") != doctor_id
                ):
                    unidentified_preference_history = True
            result.extend(
                normalize_record(item.value)
                for item in page
                if isinstance(item.value, dict)
                and item.key == item.value.get("memory_id")
                and item.value.get("doctor_id") == doctor_id
            )
            if len(page) < 100:
                break
            offset += len(page)
        # V1-only keys gain a stable, read-only identity. The first lifecycle
        # mutation persists this adapter and its projection in the same batch.
        from types import SimpleNamespace

        from .models import MemoryCandidate, new_record

        # An unidentified typed preference may own any surviving V1 projection.
        # Never mistake that projection for history-free legacy data.
        if unidentified_preference_history:
            return result
        scope = SimpleNamespace(
            doctor_id=doctor_id, patient_id=None, case_id=None, thread_id=None
        )
        offset = 0
        while True:
            page = self._store().search(
                doctor_preferences_ns(doctor_id), limit=100, offset=offset
            )
            for item in page:
                if item.key in known_keys or not isinstance(item.value, dict):
                    continue
                try:
                    record = new_record(
                        scope,
                        MemoryCandidate(
                            "doctor_preference", logical_key=item.key, data=item.value
                        ),
                        source_type="doctor",
                        source_id=doctor_id,
                    )
                except (ValueError, TypeError):
                    continue
                stamp = item.created_at.isoformat()
                record.update(
                    memory_id=f"legacy:preference:{item.key}",
                    schema_version=1,
                    created_at=stamp,
                    observed_at=stamp,
                    revision=1,
                    status=item.value.get("status", "active"),
                    valid_until=item.value.get("valid_until"),
                )
                result.append(record)
            if len(page) < 100:
                return result
            offset += len(page)

    def get_doctor_preferences(self, doctor_id: str) -> dict[str, dict]:
        self._doctor(doctor_id)
        # V1 values must pass the same adapter and source checks as typed rows.
        # A raw fallback here could revive invalid or withdrawn projections.
        preferences = {}
        typed = [
            row
            for row in self._all_doctor_records(doctor_id)
            if row.get("memory_type") == "doctor_preference"
        ]
        for key in {
            row["logical_key"]
            for row in typed
            if isinstance(row.get("logical_key"), str)
        }:
            active = [
                row
                for row in typed
                if row.get("logical_key") == key
                and is_record_active(row)
                and self._valid_doctor_record(doctor_id, row)
            ]
            if active:
                current = max(
                    active, key=lambda row: (row.get("revision", 1), row["created_at"])
                )
                preferences[key] = current["data"]
        return preferences

    @staticmethod
    def _legacy_context(
        items, *, doctor_id=None, patient_id=None, case_id=None
    ) -> dict:
        """Label incomplete legacy sources and apply lifecycle before injection."""
        result = {}
        for item in items:
            if not isinstance(item.value, dict) or not is_record_active(item.value):
                continue
            value = dict(item.value)
            if any(
                expected is not None and value.get(key) not in (None, expected)
                for key, expected in (
                    ("doctor_id", doctor_id),
                    ("patient_id", patient_id),
                    ("case_id", case_id),
                )
            ):
                continue
            if "provenance" in value:
                try:
                    normalize_provenance(value["provenance"], doctor_id=doctor_id)
                except (TypeError, ValueError):
                    continue
            value["provenance"] = {"kind": "legacy_unknown"}
            value["authority"] = "unverified_context"
            value["injection_reason"] = "active_legacy_context"
            result[item.key] = value
        return result

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
                if isinstance(item.value, dict) and is_record_active(item.value)
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
                if isinstance(item.value, dict) and is_record_active(item.value)
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
                preferences = self.get_doctor_preferences(doctor_id)
                notes = self._legacy_context(
                    store.search(
                        doctor_patient_private_ns(doctor_id, patient_id), limit=100
                    ),
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                )
                case_memories = self._legacy_context(
                    store.search(case_memory_ns(case["id"]), limit=100),
                    patient_id=patient_id,
                    case_id=case["id"],
                )
            except Exception as exc:
                logger.warning(
                    "跨会话记忆读取失败；当前病例事实仍可使用: %s",
                    type(exc).__name__,
                )
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
