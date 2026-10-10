"""Final source checks and deterministic claim conflicts before prompt injection."""

from decimal import Decimal, InvalidOperation

from martin.db import transaction
from martin.repositories.cases import CaseRepository
from martin.repositories.findings import FindingRepository
from martin.services.access_service import AccessDeniedError

from .scope import revalidate_scope

FINDING_FIELDS = frozenset({"anatomy", "diameter_mm", "finding_type", "observed_at"})


def _equal_value(field, left, right):
    if field == "diameter_mm":
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError, TypeError):
            return left is None and right is None
    if field == "observed_at":
        from .models import normalize_time

        try:
            return normalize_time(left) == normalize_time(right)
        except (TypeError, ValueError):
            return False
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and (left.strip().casefold() == right.strip().casefold())
    )


def finding_conflict(service, scope, record):
    """Compare only an explicitly targeted, authorized field; never infer a target."""
    if record.get("memory_type") not in {"clinical_claim", "correction"}:
        return None
    data = record.get("data", {})
    target, field = data.get("target_finding_id"), data.get("field")
    if not target or field not in FINDING_FIELDS or "proposed_value" not in data:
        return None
    revalidate_scope(scope, db_path=service.db_path)
    with transaction(service.db_path) as connection:
        finding = FindingRepository(connection).get_by_id(target)
        if finding is None:
            return {
                "memory_id": record["memory_id"],
                "target_type": "finding",
                "target_id": target,
                "field": field,
                "status": "target_unavailable",
                "business_fact_updated": False,
            }
        case = CaseRepository(connection).get_by_id(finding["case_id"])
        if case is None or case["patient_id"] != scope.patient_id:
            raise AccessDeniedError("Claim target is outside the authorized patient")
        value = finding[field]
        status = (
            "target_not_confirmed"
            if finding["status"] != "confirmed"
            else (
                "matches_business"
                if _equal_value(field, value, data["proposed_value"])
                else "conflict"
            )
        )
        return {
            "memory_id": record["memory_id"],
            "target_type": "finding",
            "target_id": target,
            "field": field,
            "business_value": value,
            "proposed_value": data["proposed_value"],
            "status": status,
            "business_fact_updated": False,
            "source_finding_id": target,
            "source_memory_id": record["memory_id"],
            "finding_status": finding["status"],
        }


def govern_records(service, scope, candidates):
    """A retriever hit is a candidate; current Store state decides eligibility."""
    from .lifecycle import is_record_active

    records, decisions, conflicts = [], [], []
    seen = set()
    revalidate_scope(scope, db_path=service.db_path)
    for candidate in candidates:
        memory_id = candidate.get("memory_id")
        if not memory_id or memory_id in seen:
            continue
        seen.add(memory_id)
        record = service.get_record(scope, memory_id)
        if record is None or not is_record_active(record):
            decisions.append(
                {
                    "memory_id": memory_id,
                    "eligible": False,
                    "reason": "inactive_or_source_unavailable",
                }
            )
            continue
        if not service.validate_record_source(scope, record):
            decisions.append(
                {
                    "memory_id": memory_id,
                    "eligible": False,
                    "reason": "source_not_authorized",
                }
            )
            continue
        # Preserve retrieval scores, never overwrite current source metadata.
        item = dict(record)
        for key in ("retrieval_method", "score", "relevance_score"):
            if key in candidate:
                item[key] = candidate[key]
        claim = item["memory_type"] in {"clinical_claim", "correction"}
        item["authority"] = "unverified_claim" if claim else "doctor_context"
        if claim:
            item["verification_status"] = "unverified"
        reason = "active_scoped_claim" if claim else "active_scoped_doctor_context"
        conflict = finding_conflict(service, scope, item)
        if conflict is not None:
            conflicts.append(conflict)
            item["conflict_status"] = conflict["status"]
        item["injection_reason"] = reason
        records.append(item)
        decisions.append({"memory_id": memory_id, "eligible": True, "reason": reason})
    revalidate_scope(scope, db_path=service.db_path)
    return records, decisions, conflicts
