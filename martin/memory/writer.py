"""Selective, idempotent writes with source validation and revision lineage."""

import threading
from dataclasses import dataclass, replace

from langgraph.store.base import PutOp

from .models import DERIVED_MEMORY_TYPES, MemoryCandidate, new_record
from .namespaces import doctor_records_ns, records_ns
from .scope import revalidate_scope


_write_lock = threading.RLock()


@dataclass(frozen=True)
class MemoryWriteResult:
    records: list[dict]
    deduplicated: int = 0
    index_available: bool = True
    error_code: str | None = None


class MemoryWriter:
    def __init__(self, service, vector_index=None):
        self.service = service
        self.vector_index = vector_index

    def write_interaction(
        self, scope, user_text: str, candidates: list[MemoryCandidate],
        *, interaction_id: str,
    ) -> MemoryWriteResult:
        """The selected fragment must be a literal part of this human turn."""
        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise ValueError("A source interaction ID is required")
        selected = []
        for candidate in candidates:
            candidate.validate()
            if candidate.memory_type in DERIVED_MEMORY_TYPES:
                raise ValueError("Clinical facts must be derived from business rows")
            if not candidate.text.strip() or candidate.text.strip() not in user_text:
                raise ValueError("Memory must quote a selected human fragment")
            if candidate.memory_type == "correction":
                # A statement is retrievable, but never replaces a confirmed fact.
                candidate = replace(
                    candidate, data=dict(candidate.data, business_fact_updated=False)
                )
            selected.append(candidate)
        return self.write(
            scope, selected, source_type="thread", source_id=scope.thread_id,
            interaction_id=interaction_id,
        )

    def write(
        self, scope, candidates: list[MemoryCandidate], *, source_type: str,
        source_id: str, interaction_id: str | None = None,
    ) -> MemoryWriteResult:
        revalidate_scope(scope, db_path=self.service.db_path, write=True)
        if not candidates or len(candidates) > 20:
            raise ValueError("Select between one and twenty memory fragments")
        if not source_id:
            raise ValueError("A source ID is required")
        with _write_lock:
            active = self.service.list_records(scope)
            operations, saved, deduplicated = [], [], 0
            for candidate in candidates:
                candidate.validate()
                if candidate.memory_type in DERIVED_MEMORY_TYPES:
                    raise ValueError("Use business SQL for facts and event chains")
                if not candidate.text.strip() and not candidate.data:
                    raise ValueError("Empty memory is not worth saving")
                if candidate.memory_type == "doctor_preference":
                    raise ValueError("Use the explicit report preference writer")
                if candidate.memory_type == "correction":
                    candidate = replace(
                        candidate,
                        data=dict(candidate.data, business_fact_updated=False),
                    )
                record = new_record(
                    scope, candidate, source_type=source_type, source_id=source_id,
                    interaction_id=interaction_id,
                )
                if candidate.memory_type == "workflow_preference":
                    record.update(
                        patient_id=None, case_id=None, thread_id=None,
                        source_type="doctor", source_id=scope.doctor_id,
                    )
                if not self.service.validate_record_source(scope, record):
                    raise ValueError("Memory source is outside the authorized scope")
                same_key = [item for item in active if (
                    item["memory_type"] == record["memory_type"]
                    and item["logical_key"] == record["logical_key"]
                    and item.get("patient_id") == record.get("patient_id")
                    and (
                        record["memory_type"] != "clinical_decision"
                        or item.get("case_id") == record.get("case_id")
                    )
                )]
                duplicate = next((item for item in same_key if (
                    item["text"] == record["text"] and item["data"] == record["data"]
                    and (
                        candidate.observed_at is None
                        or item["observed_at"] == record["observed_at"]
                    )
                )), None)
                if duplicate:
                    saved.append(duplicate)
                    deduplicated += 1
                    continue
                namespace = (
                    doctor_records_ns(scope.doctor_id)
                    if record["patient_id"] is None
                    else records_ns(scope.doctor_id, scope.patient_id)
                )
                for previous in same_key:
                    old = dict(
                        previous, status="superseded", superseded_by=record["memory_id"]
                    )
                    saved = [
                        old if item["memory_id"] == old["memory_id"] else item
                        for item in saved
                    ]
                    operations.append(
                        PutOp(namespace=namespace, key=old["memory_id"], value=old)
                    )
                    active.remove(previous)
                    record["supersedes"] = previous["memory_id"]
                operations.append(
                    PutOp(namespace=namespace, key=record["memory_id"], value=record)
                )
                active.append(record)
                saved.append(record)
            revalidate_scope(scope, db_path=self.service.db_path, write=True)
            if operations:
                # SqliteStore commits the whole batch, including supersede changes.
                self.service._store().batch(operations)
        semantic = any(
            item["memory_type"] in ("clinical_decision", "historical_discussion")
            for item in saved
        )
        if semantic:
            try:
                if self.vector_index is None:
                    from .vector_index import get_default_vector_index

                    self.vector_index = get_default_vector_index()
                connection = getattr(self.service._store(), "conn", None)
                reserved = [self.service.db_path] if self.service.db_path else []
                if connection is not None:
                    reserved.extend(
                        row[2] for row in connection.execute("PRAGMA database_list")
                        if row[2]
                    )
                self.vector_index.sync(
                    scope,
                    [
                        item for item in self.service.list_records(scope)
                        if item["memory_type"] in (
                            "clinical_decision", "historical_discussion"
                        )
                    ],
                    reserved_paths=reserved,
                )
            except Exception:
                # The durable source succeeded. The disposable vector can be rebuilt.
                return MemoryWriteResult(
                    saved, deduplicated, False, "semantic_index_unavailable"
                )
        return MemoryWriteResult(saved, deduplicated)
