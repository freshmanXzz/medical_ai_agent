"""Extractive derived projections with live, authorized source validation."""

import hashlib
import json
from contextlib import contextmanager

from langgraph.store.base import PutOp

from martin.db import transaction
from martin.repositories.cases import CaseRepository
from martin.repositories.patients import PatientRepository
from martin.services.access_service import AccessDeniedError, EntityNotFoundError

from .lifecycle import atomic_batch, is_record_active, write_lock
from .models import normalize_time
from .scope import revalidate_scope

SUMMARY_SOURCE_TYPES = frozenset({"clinical_decision", "historical_discussion"})


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def record_fingerprint(record: dict) -> str:
    """Include authority, lifecycle and every occurrence in the source version."""
    canonical = dict(record)
    for key in ("created_at", "observed_at", "valid_until"):
        if canonical.get(key) is not None:
            canonical[key] = normalize_time(canonical[key])
    return fingerprint(canonical)


def scope_coordinates(scope) -> dict:
    return {key: getattr(scope, key) for key in ("doctor_id", "patient_id", "case_id")}


def summaries_ns(scope) -> tuple:
    coordinates = scope_coordinates(scope)
    if any(
        not isinstance(value, str) or not value.strip() or "." in value
        for value in coordinates.values()
    ):
        raise ValueError("Summary scope requires unambiguous entity identities")
    return ("doctor", scope.doctor_id, "patient", scope.patient_id, "summaries")


def _counter(counter, text):
    if not callable(counter):
        raise ValueError("A conservative token counter is required")
    count = counter(text)
    if type(count) is not int or count < 0:
        raise ValueError("A token count must be a nonnegative integer")
    return count


def _validate_budget(budget):
    if type(budget) is not int or not 0 <= budget <= 200000:
        raise ValueError("Invalid summary token budget")


def _bounded_segments(segments, budget, counter):
    _validate_budget(budget)
    chosen = []
    for segment in segments:
        candidate = [*chosen, segment]
        if _counter(counter, "\n".join(item["text"] for item in candidate)) <= budget:
            chosen = candidate
    return chosen


def _render(record):
    text = (
        f"医生讨论，非确认业务事实 [memory:{record['memory_id']}; "
        f"case:{record['case_id']}; observed:{normalize_time(record['observed_at'])}; "
        f"confidence:{record['confidence']}]：{record['text']}"
    )
    if record.get("data"):
        text += "；医生结构化上下文：" + json.dumps(
            record["data"], ensure_ascii=False, sort_keys=True
        )
    return text


def _reference(record):
    return {
        "source_type": "memory_record",
        "memory_id": record["memory_id"],
        "doctor_id": record["doctor_id"],
        "patient_id": record["patient_id"],
        "case_id": record["case_id"],
        "observed_at": normalize_time(record["observed_at"]),
        "status": "active",
        "authority": "doctor_context",
        "memory_type": record["memory_type"],
        "confidence": record["confidence"],
        "fingerprint": record_fingerprint(record),
        "provenance": record["provenance"],
    }


def invalidate_summary_operations(service, scope, memory_ids):
    """Join lifecycle writes atomically; read validation remains authoritative."""
    ids = set(memory_ids)
    if not ids:
        return []
    namespace, operations, offset = summaries_ns(scope), [], 0
    while True:
        page = service._store().search(namespace, limit=100, offset=offset)
        for item in page:
            value = item.value
            if (
                isinstance(value, dict)
                and value.get("kind") == "rolling_summary"
                and value.get("status") == "active"
                and ids.intersection(value.get("source_memory_ids", []))
            ):
                operations.append(
                    PutOp(
                        namespace=namespace,
                        key=item.key,
                        value=dict(
                            value,
                            status="stale",
                            stale_reason="source_lifecycle_changed",
                        ),
                    )
                )
        if len(page) < 100:
            return operations
        offset += len(page)


class SummaryService:
    """Summaries are projections of raw doctor evidence, never source memories."""

    def __init__(self, service):
        self.service = service

    def eligible_sources(self, scope):
        revalidate_scope(scope, db_path=self.service.db_path)
        return [
            record
            for record in self.service.list_records(scope)
            if record["memory_type"] in SUMMARY_SOURCE_TYPES
            and record.get("doctor_id") == scope.doctor_id
            and record.get("patient_id") == scope.patient_id
            and record.get("case_id") == scope.case_id
            and record.get("provenance", {}).get("kind")
            in ("message", "api_submission")
            and is_record_active(record)
            and self.service.validate_record_source(scope, record)
        ]

    def source_version(self, records):
        return fingerprint(
            [(record["memory_id"], record_fingerprint(record)) for record in records]
        )

    def rebuild(
        self,
        scope,
        *,
        token_budget,
        token_counter,
        expected_source_version=None,
        policy_version=None,
        publication_guard=None,
    ):
        """Commit an immutable version and head only when the queued sources agree."""
        with write_lock:
            records = self.eligible_sources(scope)
            source_version = self.source_version(records)
            if (
                expected_source_version is not None
                and source_version != expected_source_version
            ):
                return self._unavailable("source_changed", scope=scope)
            namespace, head_key = summaries_ns(scope), "head:" + scope.case_id
            head = self.service._store().get(namespace, head_key)
            if (
                head
                and isinstance(head.value, dict)
                and head.value.get("source_version") == source_version
            ):
                existing = self.service._store().get(
                    namespace, head.value["summary_id"]
                )
                if (
                    existing
                    and self._valid_summary(scope, existing.value)
                    and existing.value.get("generation_token_budget") == token_budget
                    and existing.value.get("policy_version") == policy_version
                ):
                    return self.materialize(
                        scope,
                        head.value["summary_id"],
                        token_budget=token_budget,
                        token_counter=token_counter,
                    )
            references = {record["memory_id"]: _reference(record) for record in records}
            segments = [
                {"memory_id": record["memory_id"], "text": _render(record)}
                for record in records
            ]
            selected = _bounded_segments(segments, token_budget, token_counter)
            if not selected:
                return self._unavailable(
                    "summary_budget_exceeded" if records else "no_eligible_sources",
                    scope=scope,
                )
            version = (
                head.value.get("version", 0) + 1
                if head and isinstance(head.value, dict)
                else 1
            )
            summary_id = "summary:" + fingerprint(
                [scope_coordinates(scope), source_version, version]
            )
            included = [segment["memory_id"] for segment in selected]
            summary = {
                "kind": "rolling_summary",
                "summary_id": summary_id,
                "version": version,
                "scope": scope_coordinates(scope),
                "source_version": source_version,
                "status": "active",
                "authority": "derived_doctor_context",
                "created_at": normalize_time(None),
                "policy_version": policy_version,
                "generation_token_budget": token_budget,
                "source_memory_ids": included,
                "sources": [references[key] for key in included],
                "source_fingerprints": {
                    key: references[key]["fingerprint"] for key in included
                },
                "segments": selected,
                "text": "\n".join(segment["text"] for segment in selected),
                "omitted_source_memory_ids": [
                    record["memory_id"]
                    for record in records
                    if record["memory_id"] not in included
                ],
                "method": "extractive_raw_records_v1",
            }
            # A custom extractor/other connection can have changed sources during
            # generation. Never publish a projection of an obsolete snapshot.
            if self.source_version(self.eligible_sources(scope)) != source_version:
                return self._unavailable("source_changed", scope=scope)
            latest_head = self.service._store().get(namespace, head_key)
            if (latest_head.value if latest_head else None) != (
                head.value if head else None
            ):
                return self._unavailable("summary_head_changed", scope=scope)
            if publication_guard is not None and not publication_guard():
                return self._unavailable("job_claim_changed", scope=scope)
            operations = [
                PutOp(namespace=namespace, key=summary_id, value=summary),
                PutOp(
                    namespace=namespace,
                    key=head_key,
                    value={
                        "kind": "summary_head",
                        "summary_id": summary_id,
                        "version": version,
                        "source_version": source_version,
                    },
                ),
            ]
            revalidate_scope(scope, db_path=self.service.db_path)
            atomic_batch(self.service._store(), operations)
            return self.materialize(
                scope,
                summary_id,
                token_budget=token_budget,
                token_counter=token_counter,
            )

    def _valid_summary(self, scope, summary):
        if (
            not isinstance(summary, dict)
            or summary.get("kind") != "rolling_summary"
            or summary.get("status") != "active"
            or summary.get("scope") != scope_coordinates(scope)
            or summary.get("method") != "extractive_raw_records_v1"
        ):
            return False
        ids, segments, references = (
            summary.get("source_memory_ids"),
            summary.get("segments"),
            summary.get("sources"),
        )
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            return False
        if not isinstance(segments, list) or not isinstance(references, list):
            return False
        if [
            item.get("memory_id") for item in segments if isinstance(item, dict)
        ] != ids:
            return False
        if [
            item.get("memory_id") for item in references if isinstance(item, dict)
        ] != ids:
            return False
        for segment, reference in zip(segments, references):
            record = self.service.get_record(scope, segment["memory_id"])
            if (
                record is None
                or record.get("memory_type") not in SUMMARY_SOURCE_TYPES
                or any(
                    record.get(key) != getattr(scope, key)
                    for key in ("doctor_id", "patient_id", "case_id")
                )
                or record.get("provenance", {}).get("kind")
                not in ("message", "api_submission")
                or segment.get("text") != _render(record)
                or reference != _reference(record)
                or summary.get("source_fingerprints", {}).get(record["memory_id"])
                != record_fingerprint(record)
            ):
                return False
        return summary.get("text") == "\n".join(segment["text"] for segment in segments)

    @staticmethod
    def _unavailable(reason, *, scope=None, requested=True, kind="rolling_summary"):
        return {
            "kind": kind,
            "available": False,
            "requested": requested,
            "text": "",
            "sources": [],
            "source_memory_ids": [],
            "source_fingerprints": {},
            "scope": scope_coordinates(scope) if scope is not None else None,
            "omitted": 0,
            "error_code": reason,
        }

    def materialize(self, scope, summary_id, *, token_budget, token_counter):
        """Validate the entire source graph even if this request uses a subset."""
        with write_lock:
            revalidate_scope(scope, db_path=self.service.db_path)
            try:
                item = self.service._store().get(summaries_ns(scope), summary_id)
                if item is None or not self._valid_summary(scope, item.value):
                    return self._unavailable("summary_stale", scope=scope)
                summary = item.value
                selected = _bounded_segments(
                    summary["segments"], token_budget, token_counter
                )
                if not selected:
                    return self._unavailable("summary_budget_exceeded", scope=scope)
                ids = [segment["memory_id"] for segment in selected]
                original_ids = set(summary["source_memory_ids"]) | set(
                    summary["omitted_source_memory_ids"]
                )
                added = [
                    record["memory_id"]
                    for record in self.eligible_sources(scope)
                    if record["memory_id"] not in original_ids
                ]
                payload = {
                    key: summary[key]
                    for key in (
                        "kind",
                        "summary_id",
                        "version",
                        "scope",
                        "authority",
                        "method",
                        "created_at",
                        "policy_version",
                    )
                }
                payload.update(
                    available=True,
                    requested=True,
                    text="\n".join(segment["text"] for segment in selected),
                    source_memory_ids=ids,
                    source_fingerprints={
                        key: summary["source_fingerprints"][key] for key in ids
                    },
                    sources=[
                        reference
                        for reference in summary["sources"]
                        if reference["memory_id"] in ids
                    ],
                    omitted=len(summary["source_memory_ids"])
                    - len(ids)
                    + len(summary["omitted_source_memory_ids"])
                    + len(added),
                    omitted_source_memory_ids=[
                        key for key in summary["source_memory_ids"] if key not in ids
                    ]
                    + summary["omitted_source_memory_ids"]
                    + added,
                    newer_source_memory_ids=added,
                    error_code=None,
                )
                return payload
            except (AccessDeniedError, EntityNotFoundError):
                raise
            except Exception:
                return self._unavailable("summary_store_unavailable", scope=scope)

    def detailed_for_task(self, scope, task, *, token_budget, token_counter):
        from .router import RetrievalPlan

        plan = RetrievalPlan.for_query(task)
        if not (plan.semantic or plan.temporal):
            result = self._unavailable(None, scope=scope, requested=False)
            return dict(result, available=True)
        with write_lock:
            revalidate_scope(scope, db_path=self.service.db_path)
            try:
                head = self.service._store().get(
                    summaries_ns(scope), "head:" + scope.case_id
                )
                if head is None:
                    return self._unavailable("summary_not_built", scope=scope)
                return self.materialize(
                    scope,
                    head.value["summary_id"],
                    token_budget=token_budget,
                    token_counter=token_counter,
                )
            except (AccessDeniedError, EntityNotFoundError):
                raise
            except Exception:
                return self._unavailable("summary_store_unavailable", scope=scope)

    def minimal_background(self, scope, *, token_budget, token_counter):
        if scope is None or not getattr(scope, "patient_id", None):
            result = self._unavailable(None, requested=False, kind="minimal_background")
            return dict(result, available=True)
        with write_lock:
            revalidate_scope(scope, db_path=self.service.db_path)
            with transaction(self.service.db_path) as connection:
                patient = PatientRepository(connection).get_by_id(scope.patient_id)
                case = CaseRepository(connection).get_by_id(scope.case_id)
                records = [
                    ("patient", dict(patient), ("sex", "birth_date")),
                    (
                        "case",
                        dict(case),
                        (
                            "age_at_encounter_years",
                            "age_recorded_at",
                            "smoking_history",
                            "family_history",
                        ),
                    ),
                ]
                segments, sources = [], []
                for kind, row, keys in records:
                    data = {key: row[key] for key in keys if row.get(key) is not None}
                    if not data:
                        continue
                    reference = {
                        "source_type": kind,
                        "source_id": row["id"],
                        "doctor_id": scope.doctor_id,
                        "patient_id": scope.patient_id,
                        "case_id": scope.case_id,
                        "observed_at": row["updated_at"],
                        "authority": "confirmed_business_fact",
                        "fingerprint": fingerprint(row),
                    }
                    identity = kind + ":" + row["id"]
                    text = (
                        f"确认业务背景 [{identity}; observed:{row['updated_at']}]："
                        + json.dumps(data, ensure_ascii=False, sort_keys=True)
                    )
                    segments.append({"memory_id": identity, "text": text})
                    sources.append(reference)
                chosen = _bounded_segments(segments, token_budget, token_counter)
                ids = [item["memory_id"] for item in chosen]
                return {
                    "kind": "minimal_background",
                    "available": True,
                    "requested": True,
                    "scope": scope_coordinates(scope),
                    "text": "\n".join(item["text"] for item in chosen),
                    "sources": [
                        item
                        for item in sources
                        if item["source_type"] + ":" + item["source_id"] in ids
                    ],
                    "omitted": len(segments) - len(chosen),
                    "error_code": None,
                }

    def validate_materialized(self, scope, payload):
        """Final dispatch guard; cached text is never itself authoritative."""
        with write_lock:
            revalidate_scope(scope, db_path=self.service.db_path)
            if not isinstance(payload, dict) or payload.get(
                "scope"
            ) != scope_coordinates(scope):
                return False
            if not payload.get("requested"):
                return payload.get("text") == ""
            if not payload.get("available"):
                return False
            try:
                if payload.get("kind") == "minimal_background":
                    expected_text, seen = [], set()
                    with transaction(self.service.db_path) as connection:
                        for source in payload.get("sources", []):
                            kind = source.get("source_type")
                            row = (
                                PatientRepository(connection).get_by_id(
                                    scope.patient_id
                                )
                                if kind == "patient"
                                else (
                                    CaseRepository(connection).get_by_id(scope.case_id)
                                    if kind == "case"
                                    else None
                                )
                            )
                            if (
                                row is None
                                or row["id"] != source.get("source_id")
                                or source.get("fingerprint") != fingerprint(dict(row))
                            ):
                                return False
                            if kind in seen:
                                return False
                            seen.add(kind)
                            expected_reference = {
                                "source_type": kind,
                                "source_id": row["id"],
                                "doctor_id": scope.doctor_id,
                                "patient_id": scope.patient_id,
                                "case_id": scope.case_id,
                                "observed_at": row["updated_at"],
                                "authority": "confirmed_business_fact",
                                "fingerprint": fingerprint(dict(row)),
                            }
                            if source != expected_reference:
                                return False
                            keys = (
                                ("sex", "birth_date")
                                if kind == "patient"
                                else (
                                    "age_at_encounter_years",
                                    "age_recorded_at",
                                    "smoking_history",
                                    "family_history",
                                )
                            )
                            data = {
                                key: row[key] for key in keys if row[key] is not None
                            }
                            expected_text.append(
                                f"确认业务背景 [{kind}:{row['id']}; observed:{row['updated_at']}]："
                                + json.dumps(data, ensure_ascii=False, sort_keys=True)
                            )
                    return payload.get("text") == "\n".join(expected_text)
                if payload.get("kind") != "rolling_summary":
                    return False
                item = self.service._store().get(
                    summaries_ns(scope), payload.get("summary_id", "")
                )
                if item is None or not self._valid_summary(scope, item.value):
                    return False
                summary, ids = item.value, payload.get("source_memory_ids", [])
                if (
                    not ids
                    or payload.get("version") != summary["version"]
                    or not set(ids).issubset(summary["source_memory_ids"])
                ):
                    return False
                text = "\n".join(
                    segment["text"]
                    for segment in summary["segments"]
                    if segment["memory_id"] in ids
                )
                return (
                    payload.get("text") == text
                    and payload.get("source_fingerprints")
                    == {key: summary["source_fingerprints"][key] for key in ids}
                    and payload.get("sources")
                    == [
                        reference
                        for reference in summary["sources"]
                        if reference["memory_id"] in ids
                    ]
                )
            except (AccessDeniedError, EntityNotFoundError):
                raise
            except Exception:
                return False

    @contextmanager
    def verified_for_injection(self, scope, payload):
        """Serialize source validation and dispatch with in-process mutations."""
        with write_lock:
            yield self.validate_materialized(scope, payload)
