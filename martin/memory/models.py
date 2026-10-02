"""Typed, source-labelled memory; clinical facts remain in the business DB."""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


MEMORY_TYPES = frozenset(
    {
        "doctor_preference",
        "workflow_preference",
        "patient_fact",
        "medical_observation",
        "clinical_decision",
        "case_evolution",
        "historical_discussion",
        "task_followup",
        "correction",
    }
)
EXACT_MEMORY_TYPES = frozenset(
    {"doctor_preference", "workflow_preference", "correction", "task_followup"}
)
SEMANTIC_MEMORY_TYPES = frozenset({"clinical_decision", "historical_discussion"})
DERIVED_MEMORY_TYPES = frozenset(
    {"patient_fact", "medical_observation", "case_evolution"}
)


def _validate_data(data: dict) -> None:
    """Accept bounded JSON values and exclude reasoning at every nesting level."""
    try:
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Memory data must contain finite JSON values") from exc
    if len(encoded) > 4000:
        raise ValueError("Memory data is too large")
    pending = [data]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError("Memory data keys must be strings")
                if key.casefold() in ("reasoning", "reasoning_content"):
                    raise ValueError("Reasoning cannot enter long-term memory")
                pending.append(child)
        elif isinstance(value, list):
            pending.extend(value)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Memory data must contain JSON values")


def normalize_time(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A valid ISO observation time is required")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class MemoryCandidate:
    memory_type: str
    text: str = ""
    logical_key: str | None = None
    data: dict = field(default_factory=dict)
    observed_at: str | None = None
    confidence: float = 1.0

    def validate(self) -> None:
        if (
            not isinstance(self.memory_type, str)
            or self.memory_type not in MEMORY_TYPES
        ):
            raise ValueError("Unknown memory type")
        if not isinstance(self.text, str) or len(self.text) > 1200:
            raise ValueError("Memory text must be a bounded fragment")
        if not isinstance(self.data, dict):
            raise ValueError("Memory data must be an object")
        if self.logical_key is not None and (
            not isinstance(self.logical_key, str)
            or not self.logical_key.strip()
            or len(self.logical_key) > 120
        ):
            raise ValueError("Invalid memory key")
        if type(self.confidence) not in (int, float) or (
            not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("Invalid memory confidence")
        _validate_data(self.data)
        if self.observed_at is not None:
            normalize_time(self.observed_at)

    def key(self) -> str:
        if self.logical_key:
            return self.logical_key
        content = json.dumps(
            {"text": self.text.strip(), "data": self.data},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


def new_record(
    scope,
    candidate: MemoryCandidate,
    *,
    source_type: str,
    source_id: str,
    interaction_id: str | None = None,
) -> dict:
    candidate.validate()
    now = normalize_time(None)
    return {
        "memory_id": str(uuid4()),
        "memory_type": candidate.memory_type,
        "doctor_id": scope.doctor_id,
        "patient_id": scope.patient_id,
        "case_id": scope.case_id,
        "thread_id": scope.thread_id,
        "source_type": source_type,
        "source_id": source_id,
        "interaction_id": interaction_id,
        "created_at": now,
        "observed_at": (
            normalize_time(candidate.observed_at) if candidate.observed_at else now
        ),
        "status": "active",
        "confidence": float(candidate.confidence),
        "text": candidate.text.strip(),
        "data": dict(candidate.data),
        "logical_key": candidate.key(),
        "supersedes": None,
    }
