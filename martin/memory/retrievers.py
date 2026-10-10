"""Exact Store records and temporal business facts have separate retrieval paths."""

import json
import logging
import math
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from martin.db import transaction
from martin.repositories.findings import FindingRepository
from martin.services.access_service import AccessDeniedError, EntityNotFoundError

from .context import MemorySnapshot
from .scope import MemoryScope, _authorize_scope_on_connection

logger = logging.getLogger(__name__)

EXACT_RECORD_TYPES = frozenset(
    {
        "doctor_preference",
        "workflow_preference",
        "correction",
        "task_followup",
        "clinical_claim",
    }
)


class ExactRetriever:
    """Use explicit namespaces and business columns without embedding or Top-K."""

    def __init__(self, service):
        self.service = service

    def retrieve(self, scope: MemoryScope, query: str = "") -> MemorySnapshot:
        with transaction(self.service.db_path) as connection:
            connection.execute("BEGIN")
            _authorize_scope_on_connection(
                connection,
                scope.doctor_id,
                scope.thread_id,
                patient_id=scope.patient_id,
                case_id=scope.case_id,
            )
            row = connection.execute(
                """SELECT patients.sex, patients.birth_date,
                   cases.age_at_encounter_years, cases.age_recorded_at,
                   cases.smoking_history, cases.family_history
                   FROM patients JOIN cases ON cases.patient_id = patients.id
                   WHERE patients.id = ? AND cases.id = ?""",
                (scope.patient_id, scope.case_id),
            ).fetchone()
            facts = {
                "patient_id": scope.patient_id,
                "case_id": scope.case_id,
                "sex": row["sex"],
                "birth_date": row["birth_date"],
                "age_at_encounter_years": row["age_at_encounter_years"],
                "age_recorded_at": row["age_recorded_at"],
                "smoking_history": row["smoking_history"],
                "family_history": row["family_history"],
                "sources": [
                    {"source_type": "patient", "source_id": scope.patient_id},
                    {"source_type": "case", "source_id": scope.case_id},
                ],
            }
        snapshot = self.service.snapshot_for_thread(scope.doctor_id, scope.thread_id)
        records = []
        if snapshot.available:
            try:
                records = [
                    record
                    for record in self.service.list_records(scope)
                    if record.get("memory_type") in EXACT_RECORD_TYPES
                    and record.get("status") == "active"
                    and self.service.validate_record_source(scope, record)
                ]
            except (AccessDeniedError, EntityNotFoundError):
                raise
            except Exception:
                logger.warning("Typed exact memory is temporarily unavailable")
                snapshot = replace(
                    snapshot,
                    available=False,
                    error_code="store_unavailable",
                    warning="Long-term memory is temporarily unavailable.",
                    doctor_preferences={},
                    private_notes={},
                    historical_observations=[],
                    case_memories={},
                )
        return replace(snapshot, patient_facts=facts, typed_records=records)


def _utc_time(value: str) -> datetime:
    """Legacy naive and date-only times are interpreted as UTC, never local time."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Observed time must be a non-empty ISO date or datetime")
    instant = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


class TemporalRetriever:
    """Read confirmed observations directly from the authorized business DB."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def retrieve(
        self,
        scope: MemoryScope,
        *,
        finding_type: str | None = None,
        body_location: str | None = None,
        observed_after: str | None = None,
        observed_before: str | None = None,
        source_finding_id: str | None = None,
        lesion_id: str | None = None,
    ) -> dict:
        warnings: list[str] = []
        events = []
        with transaction(self.db_path) as connection:
            connection.execute("BEGIN")
            _authorize_scope_on_connection(
                connection,
                scope.doctor_id,
                scope.thread_id,
                patient_id=scope.patient_id,
                case_id=scope.case_id,
            )
            after = _utc_time(observed_after) if observed_after is not None else None
            before = _utc_time(observed_before) if observed_before is not None else None
            if after is not None and before is not None and after > before:
                raise ValueError("Observed time range is reversed")
            rows = FindingRepository(connection).list_by_patient(scope.patient_id)
            current_times = []
            for row in rows:
                if row["status"] == "confirmed" and row["case_id"] == scope.case_id:
                    try:
                        current_times.append(_utc_time(row["observed_at"]))
                    except (ValueError, OverflowError):
                        continue
            anchor = max(current_times) if current_times else None
            if anchor is None:
                warnings.append("current_observation_unavailable")
            for row in rows:
                if row["status"] != "confirmed":
                    continue
                if finding_type is not None and row["finding_type"] != finding_type:
                    continue
                if body_location is not None and row["anatomy"] != body_location:
                    continue
                if source_finding_id is not None and row["id"] != source_finding_id:
                    continue
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                stable_id = payload.get("lesion_id")
                if not isinstance(stable_id, str) or not stable_id.strip():
                    stable_id = None
                if lesion_id is not None and stable_id != lesion_id:
                    continue
                try:
                    observed = _utc_time(row["observed_at"])
                except (ValueError, OverflowError):
                    warnings.append("invalid_observed_at")
                    continue
                if (
                    anchor is not None
                    and row["case_id"] != scope.case_id
                    and observed > anchor
                ):
                    continue
                if after is not None and observed < after:
                    continue
                if before is not None and observed > before:
                    continue
                diameter = row["diameter_mm"]
                if diameter is not None and not math.isfinite(diameter):
                    diameter = None
                    warnings.append("invalid_measurement")
                events.append(
                    {
                        "finding_id": row["id"],
                        "source_finding_id": row["id"],
                        "source_type": "finding",
                        "source_id": row["id"],
                        "doctor_id": scope.doctor_id,
                        "patient_id": scope.patient_id,
                        "case_id": row["case_id"],
                        "thread_id": scope.thread_id,
                        "source_case_id": row["case_id"],
                        "source_attachment_id": row["source_attachment_id"],
                        "finding_type": row["finding_type"],
                        "body_location": row["anatomy"],
                        "anatomy": row["anatomy"],
                        "diameter_mm": diameter,
                        "observed_at": observed.isoformat(),
                        "created_at": row["created_at"],
                        "status": row["status"],
                        "confidence": 1.0,
                        "current": row["case_id"] == scope.case_id,
                        "lesion_id": stable_id,
                    }
                )
        events.sort(key=lambda event: (event["observed_at"], event["finding_id"]))
        changes = self._changes(events, warnings) if anchor is not None else []
        return {
            "events": events,
            "changes": changes,
            "warnings": list(dict.fromkeys(warnings)),
        }

    @staticmethod
    def _changes(events: list[dict], warnings: list[str]) -> list[dict]:
        groups = defaultdict(list)
        for event in events:
            if event["lesion_id"] is not None:
                key = (event["finding_type"], "lesion_id", event["lesion_id"])
            else:
                key = (event["finding_type"], "anatomy", event["anatomy"])
            groups[key].append(event)
        changes = []
        for (_, basis, _), candidates in groups.items():
            if len(candidates) < 2:
                continue
            times = [event["observed_at"] for event in candidates]
            # Unknown lesion identity plus multiple observations from one case
            # cannot be treated as successive examinations of the same lesion.
            cases = [event["case_id"] for event in candidates]
            if len(times) != len(set(times)) or (
                basis != "lesion_id" and len(cases) != len(set(cases))
            ):
                warnings.append("ambiguous_observations")
                continue
            if basis != "lesion_id":
                if not candidates[0]["anatomy"]:
                    warnings.append("lesion_identity_unconfirmed")
                    continue
                warnings.append("lesion_identity_unconfirmed")
            for previous, current in zip(candidates, candidates[1:]):
                if previous["diameter_mm"] is None or current["diameter_mm"] is None:
                    warnings.append("measurement_unavailable")
                    continue
                changes.append(
                    {
                        "previous_finding_id": previous["finding_id"],
                        "current_finding_id": current["finding_id"],
                        "source_finding_ids": [
                            previous["finding_id"],
                            current["finding_id"],
                        ],
                        "from_observed_at": previous["observed_at"],
                        "to_observed_at": current["observed_at"],
                        "from_mm": previous["diameter_mm"],
                        "to_mm": current["diameter_mm"],
                        "delta_mm": current["diameter_mm"] - previous["diameter_mm"],
                        "finding_type": current["finding_type"],
                        "body_location": current["anatomy"],
                        "lesion_id": current["lesion_id"],
                        "match_basis": (
                            "lesion_id"
                            if basis == "lesion_id"
                            else "single_observation_per_time"
                        ),
                    }
                )
        changes.sort(
            key=lambda change: (change["to_observed_at"], change["current_finding_id"])
        )
        return changes
