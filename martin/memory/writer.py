"""Selective, idempotent writes with source validation and revision lineage."""

import math
from dataclasses import dataclass, field, replace

from langgraph.store.base import PutOp

from martin.db import transaction
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.services.access_service import EntityNotFoundError

from .deduplication import HIGH_RISK_TYPES, low_risk_equivalent, reinforce
from .lifecycle import (
    atomic_batch,
    is_record_active,
    lifecycle_event,
    normalize_provenance,
    write_lock,
)
from .models import DERIVED_MEMORY_TYPES, MemoryCandidate, new_record, normalize_time
from .namespaces import doctor_records_ns, records_ns
from .scope import revalidate_scope


@dataclass(frozen=True)
class MemoryWriteResult:
    records: list[dict]
    deduplicated: int = 0
    index_available: bool = True
    error_code: str | None = None
    decisions: list[dict] = field(default_factory=list)
    governance_job: dict | None = None


class MemoryWriter:
    def __init__(self, service, vector_index=None):
        self.service = service
        self.vector_index = vector_index

    def write_interaction(
        self, scope, user_text: str, candidates: list[MemoryCandidate],
        *, interaction_id: str,
    ) -> MemoryWriteResult:
        """Bind selected literal human fragments to the actual runtime message."""
        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise ValueError("A source interaction ID is required")
        for candidate in candidates:
            candidate.validate()
            if candidate.memory_type in DERIVED_MEMORY_TYPES:
                raise ValueError("Clinical facts must be derived from business rows")
            if not candidate.text.strip() or candidate.text.strip() not in user_text:
                raise ValueError("Memory must quote a selected human fragment")
        return self.write(
            scope,
            candidates,
            source_type="thread",
            source_id=scope.thread_id,
            interaction_id=interaction_id,
            provenance={
                "kind": "message",
                "actor_id": scope.doctor_id,
                "actor_role": "doctor",
                "message_id": interaction_id,
                "thread_id": scope.thread_id,
            },
        )

    def _prepare_candidate(self, scope, candidate):
        candidate.validate()
        if candidate.memory_type in DERIVED_MEMORY_TYPES:
            raise ValueError("Use business SQL for facts and event chains")
        if not candidate.text.strip() and not candidate.data:
            raise ValueError("Empty memory is not worth saving")
        if candidate.memory_type == "doctor_preference":
            raise ValueError("Use the explicit report preference writer")
        if candidate.memory_type in ("correction", "clinical_claim"):
            data = dict(
                candidate.data,
                business_fact_updated=False,
                verification_status="unverified",
            )
            target_fields = {"target_finding_id", "field", "proposed_value"}
            if target_fields.intersection(data):
                if not target_fields.issubset(data):
                    raise ValueError(
                        "A Finding claim requires target, field and proposed value"
                    )
                target, field, value = (
                    data[key]
                    for key in ("target_finding_id", "field", "proposed_value")
                )
                if not isinstance(target, str) or not target.strip():
                    raise ValueError("A Finding claim requires an explicit target ID")
                if not isinstance(field, str) or field not in {
                    "anatomy",
                    "diameter_mm",
                    "finding_type",
                    "observed_at",
                }:
                    raise ValueError("Unsupported Finding claim field")
                if field == "diameter_mm":
                    if (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise ValueError(
                            "Proposed diameter must be a finite nonnegative number"
                        )
                elif (
                    not isinstance(value, str) or not value.strip() or len(value) > 200
                ):
                    raise ValueError("Proposed Finding value must be a bounded string")
                elif field == "observed_at":
                    data["proposed_value"] = normalize_time(value)
                with transaction(self.service.db_path) as connection:
                    finding = FindingRepository(connection).get_by_id(target)
                    case = (
                        CaseRepository(connection).get_by_id(finding["case_id"])
                        if finding
                        else None
                    )
                    if case is None or case["patient_id"] != scope.patient_id:
                        raise ValueError(
                            "Finding target is outside the authorized patient"
                        )
            candidate = replace(candidate, data=data)
        return candidate

    @staticmethod
    def _same_identity(item, record):
        return (
            item["memory_type"] == record["memory_type"]
            and item["logical_key"] == record["logical_key"]
            and item.get("patient_id") == record.get("patient_id")
            and item.get("case_id") == record.get("case_id")
        )

    @staticmethod
    def _same_content(item, record, candidate):
        return (
            item["text"] == record["text"]
            and item["data"] == record["data"]
            and item.get("confidence") == candidate.confidence
            and item.get("valid_until") == record.get("valid_until")
            and (
                candidate.observed_at is None
                or item["observed_at"] == record["observed_at"]
            )
        )

    def revise(self, scope, memory_id, candidate, *, reason="", provenance=None):
        """Revise an explicit active identity; a retry may return its same successor."""
        revalidate_scope(scope, db_path=self.service.db_path, write=True)
        provenance = normalize_provenance(provenance, doctor_id=scope.doctor_id)
        if provenance["kind"] == "business_event":
            raise ValueError("Authored memory cannot claim business event provenance")
        if provenance.get("thread_id") not in (None, scope.thread_id):
            raise ValueError("Write provenance must identify the current thread")
        lifecycle_event(
            "revise", memory_id, scope.doctor_id, reason=reason, provenance=provenance
        )
        with write_lock:
            previous = self.service.get_record(scope, memory_id, include_inactive=True)
            if previous is None:
                raise EntityNotFoundError("Memory not found")
            if candidate.memory_type != previous["memory_type"]:
                raise ValueError("A revision cannot change memory type")
            if candidate.logical_key not in (None, previous["logical_key"]):
                raise ValueError("A revision cannot change memory identity")
            candidate = replace(candidate, logical_key=previous["logical_key"])
            prepared = self._prepare_candidate(scope, candidate)
            if not is_record_active(previous):
                successor = (
                    self.service.get_record(scope, previous.get("superseded_by", ""))
                    if previous["status"] == "superseded"
                    else None
                )
                if successor and self._same_content(
                    successor,
                    {
                        "text": prepared.text.strip(),
                        "data": prepared.data,
                        "valid_until": (
                            normalize_time(prepared.valid_until)
                            if prepared.valid_until
                            else None
                        ),
                        "observed_at": normalize_time(prepared.observed_at),
                    },
                    prepared,
                ):
                    return MemoryWriteResult([successor], 1)
                raise ValueError("Only an active memory can be revised")
            # Preserve case-scoped decision identity when editing from a later thread.
            if (
                previous["memory_type"] == "clinical_decision"
                and previous.get("case_id") != scope.case_id
            ):
                raise ValueError("Revise a clinical decision from its original case")
            return self.write(
                scope,
                [prepared],
                source_type="thread",
                source_id=scope.thread_id,
                provenance=provenance,
                reason=reason,
                _revision_target_id=memory_id,
            )

    def write(
        self,
        scope,
        candidates: list[MemoryCandidate],
        *,
        source_type: str,
        source_id: str,
        interaction_id: str | None = None,
        provenance=None,
        reason: str = "",
        _revision_target_id: str | None = None,
    ) -> MemoryWriteResult:
        revalidate_scope(scope, db_path=self.service.db_path, write=True)
        if not candidates or len(candidates) > 20:
            raise ValueError("Select between one and twenty memory fragments")
        if not source_id:
            raise ValueError("A source ID is required")
        provenance = normalize_provenance(provenance, doctor_id=scope.doctor_id)
        if provenance["kind"] == "business_event":
            raise ValueError("Authored memory cannot claim business event provenance")
        if provenance.get("thread_id") not in (None, scope.thread_id):
            raise ValueError("Write provenance must identify the current thread")
        if provenance["kind"] == "message":
            if (
                interaction_id is not None
                and interaction_id != provenance["message_id"]
            ):
                raise ValueError("Interaction and source message IDs differ")
            interaction_id = provenance["message_id"]
        elif provenance["kind"] == "api_submission" and interaction_id is not None:
            raise ValueError("An API submission cannot claim a message interaction")
        lifecycle_event(
            "write", "", scope.doctor_id, reason=reason, provenance=provenance
        )
        with write_lock:
            history = self.service.list_records(scope, include_inactive=True)
            operations, saved, deduplicated, decisions = [], [], 0, []
            for candidate in candidates:
                candidate = self._prepare_candidate(scope, candidate)
                record = new_record(
                    scope,
                    candidate,
                    source_type=source_type,
                    source_id=source_id,
                    interaction_id=interaction_id,
                    provenance=provenance,
                )
                if candidate.memory_type in ("clinical_claim", "correction"):
                    record["verification_status"] = "unverified"
                    record["authority"] = "unverified_claim"
                if candidate.memory_type == "workflow_preference":
                    record.update(
                        patient_id=None,
                        case_id=None,
                        thread_id=None,
                        source_type="doctor",
                        source_id=scope.doctor_id,
                    )
                if not self.service.validate_record_source(scope, record):
                    raise ValueError("Memory source is outside the authorized scope")
                same_key = [
                    item for item in history if self._same_identity(item, record)
                ]
                active = [item for item in same_key if is_record_active(item)]
                duplicate = next(
                    (
                        item
                        for item in active
                        if (
                            _revision_target_id is None
                            or item["memory_id"] == _revision_target_id
                        )
                        if self._same_content(item, record, candidate)
                    ),
                    None,
                )
                if (
                    duplicate
                    and candidate.memory_type in HIGH_RISK_TYPES
                    and (
                        candidate.observed_at is None
                        and duplicate.get("provenance") != record["provenance"]
                    )
                ):
                    # Equal words at an unspecified later time are not necessarily
                    # the same clinical event. Only a source retry is idempotent.
                    duplicate = None
                duplicate_reason = "exact_duplicate"
                if duplicate is None and _revision_target_id is None:
                    duplicate = next(
                        (
                            item
                            for item in history
                            if is_record_active(item)
                            and low_risk_equivalent(item, record, candidate)
                        ),
                        None,
                    )
                    duplicate_reason = "low_risk_equivalent"
                if duplicate:
                    strengthened = reinforce(duplicate, record, reason=duplicate_reason)
                    if strengthened is not duplicate:
                        namespace = (
                            doctor_records_ns(scope.doctor_id)
                            if duplicate.get("patient_id") is None
                            else records_ns(scope.doctor_id, scope.patient_id)
                        )
                        if not self.service.validate_record_source(scope, strengthened):
                            raise ValueError(
                                "Reinforced source is outside the authorized scope"
                            )
                        operations.append(
                            PutOp(
                                namespace=namespace,
                                key=duplicate["memory_id"],
                                value=strengthened,
                            )
                        )
                        history[history.index(duplicate)] = strengthened
                        saved = [
                            (
                                strengthened
                                if item["memory_id"] == duplicate["memory_id"]
                                else item
                            )
                            for item in saved
                        ]
                    saved.append(strengthened)
                    deduplicated += 1
                    decisions.append(
                        {
                            "memory_id": strengthened["memory_id"],
                            "reason": duplicate_reason,
                            "merged": True,
                        }
                    )
                    continue
                namespace = (
                    doctor_records_ns(scope.doctor_id)
                    if record["patient_id"] is None
                    else records_ns(scope.doctor_id, scope.patient_id)
                )
                replacing = (
                    [
                        item
                        for item in history
                        if item["memory_id"] == _revision_target_id
                        and is_record_active(item)
                    ]
                    if _revision_target_id is not None
                    else active if candidate.memory_type == "task_followup" else []
                )
                record["revision"] = (
                    max(
                        (item.get("revision", 1) for item in [*same_key, *replacing]),
                        default=0,
                    )
                    + 1
                    if replacing or candidate.memory_type == "task_followup"
                    else 1
                )
                for previous in replacing:
                    event = lifecycle_event(
                        "supersede",
                        previous["memory_id"],
                        scope.doctor_id,
                        reason=reason,
                        provenance=provenance,
                    )
                    old = dict(
                        previous,
                        status="superseded",
                        superseded_by=record["memory_id"],
                        audit_events=[*previous.get("audit_events", []), event],
                    )
                    saved = [
                        old if item["memory_id"] == old["memory_id"] else item
                        for item in saved
                    ]
                    operations.append(
                        PutOp(namespace=namespace, key=old["memory_id"], value=old)
                    )
                    history[history.index(previous)] = old
                    record["supersedes"] = previous["memory_id"]
                if not active and same_key and candidate.memory_type == "task_followup":
                    record["supersedes"] = max(
                        same_key,
                        key=lambda item: (item.get("revision", 1), item["created_at"]),
                    )["memory_id"]
                operations.append(
                    PutOp(namespace=namespace, key=record["memory_id"], value=record)
                )
                history.append(record)
                saved.append(record)
                decisions.append(
                    {
                        "memory_id": record["memory_id"],
                        "merged": False,
                        "reason": (
                            "explicit_revision"
                            if replacing
                            else (
                                "high_risk_independent"
                                if candidate.memory_type in HIGH_RISK_TYPES
                                else "new_or_refined_preference"
                            )
                        ),
                    }
                )
            revalidate_scope(scope, db_path=self.service.db_path, write=True)
            if operations:
                from .summaries import invalidate_summary_operations

                changed = [operation.key for operation in operations if operation.value]
                operations.extend(
                    invalidate_summary_operations(self.service, scope, changed)
                )
                atomic_batch(self.service._store(), operations)
        governance_job = None
        try:
            from .governance_jobs import enqueue_from_policy

            governance_job = enqueue_from_policy(self.service, scope)
        except Exception:
            # The original record is already committed. Queue failure must not
            # masquerade as failure to save that evidence or block ordinary chat.
            governance_job = {
                "queued": False,
                "error_code": "summary_queue_unavailable",
            }
        if any(
            item["memory_type"] in ("clinical_decision", "historical_discussion")
            for item in saved
        ):
            try:
                if self.vector_index is None:
                    from .vector_index import get_default_vector_index

                    self.vector_index = get_default_vector_index()
                connection = getattr(self.service._store(), "conn", None)
                reserved = [self.service.db_path] if self.service.db_path else []
                if connection is not None:
                    reserved.extend(
                        row[2]
                        for row in connection.execute("PRAGMA database_list")
                        if row[2]
                    )
                self.vector_index.sync(
                    scope,
                    [
                        item
                        for item in self.service.list_records(scope)
                        if item["memory_type"]
                        in ("clinical_decision", "historical_discussion")
                    ],
                    reserved_paths=reserved,
                )
            except Exception:
                return MemoryWriteResult(
                    saved,
                    deduplicated,
                    False,
                    "semantic_index_unavailable",
                    decisions,
                    governance_job,
                )
        return MemoryWriteResult(
            saved, deduplicated, decisions=decisions, governance_job=governance_job
        )
