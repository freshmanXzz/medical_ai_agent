"""Conservative equivalence rules; similarity never establishes clinical identity."""

import re

HIGH_RISK_TYPES = frozenset(
    {"clinical_decision", "historical_discussion", "clinical_claim", "correction"}
)


def workflow_equivalence(text: str) -> str | None:
    """Recognize a small measured vocabulary, without removing conditions.

    Unknown language stays independent. Numbers, dates, exceptions and negation
    deliberately have no near-equivalence rule; exact matching still works.
    """
    value = re.sub(r"[\s，。！？、,:;.!?；：]", "", text)
    if re.search(r"\d|不|未|无|除|如果|若|仅|复杂|常规|普通|当|时|每|曾|已经", value):
        return None
    rules = (
        (
            r"(?:以后|今后|将来)?(?:报告|写报告)(?:请)?"
            r"(?:结论前置|先给结论|先写结论|先列结论|先说明结论|把结论放前面)",
            "report:conclusion_first",
        ),
        (
            r"(?:以后|今后|将来)?(?:分析|影像分析)(?:请)?"
            r"(?:先列数据限制|先说明数据限制|先列资料限制|先说明资料限制)",
            "analysis:limitations_first",
        ),
    )
    for expression, identity in rules:
        if re.fullmatch(expression, value):
            return identity
    return None


def low_risk_equivalent(previous: dict, record: dict, candidate) -> bool:
    """Require the same doctor, scope, structured content and time semantics."""
    if record["memory_type"] != "workflow_preference":
        return False
    if any(
        previous.get(key) != record.get(key)
        for key in (
            "doctor_id",
            "patient_id",
            "case_id",
            "memory_type",
            "data",
            "valid_until",
        )
    ):
        return False
    if previous.get("confidence") != candidate.confidence:
        return False
    if (
        candidate.observed_at is not None
        and previous["observed_at"] != record["observed_at"]
    ):
        return False
    left, right = workflow_equivalence(previous["text"]), workflow_equivalence(
        record["text"]
    )
    return left is not None and left == right


def source_reference(record: dict) -> dict:
    """Keep the actual occurrence rather than inventing a source message."""
    return {
        "provenance": record["provenance"],
        "source_type": record["source_type"],
        "source_id": record["source_id"],
        "source_message_id": record.get("source_message_id"),
        "interaction_id": record.get("interaction_id"),
        "doctor_id": record["doctor_id"],
        "patient_id": record.get("patient_id"),
        "case_id": record.get("case_id"),
        "thread_id": record.get("thread_id"),
        "observed_at": record["observed_at"],
        "text": record["text"],
    }


def reinforce(previous: dict, record: dict, *, reason: str) -> dict:
    """Append a distinct validated occurrence; retrying it is idempotent."""
    reference = source_reference(record)
    coordinates = lambda item: (
        item["provenance"],
        item["source_type"],
        item["source_id"],
        item["text"],
    )
    existing = [source_reference(previous), *previous.get("reinforced_sources", [])]
    if any(coordinates(item) == coordinates(reference) for item in existing):
        return previous
    return dict(
        previous,
        reinforced_sources=[*previous.get("reinforced_sources", []), reference],
        deduplication_events=[
            *previous.get("deduplication_events", []),
            {
                "reason": reason,
                "provenance": record["provenance"],
                "observed_at": record["observed_at"],
            },
        ],
    )
