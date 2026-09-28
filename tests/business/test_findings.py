"""Confirmed findings are durable, actor-scoped business facts."""

import pytest

from martin.db import connect
from martin.services.access_service import AccessDeniedError
from martin.services.fact_service import FactService


def test_confirmed_finding_persisted(entity_db):
    service = FactService(entity_db)
    finding_id = service.add_finding(
        "D001", "C001", "nodule", "2026-09-28T00:00:00+00:00", diameter_mm=7.5
    )
    with connect(entity_db) as connection:
        row = connection.execute(
            "SELECT case_id, status, diameter_mm FROM findings WHERE id = ?",
            (finding_id,),
        ).fetchone()
    assert tuple(row) == ("C001", "confirmed", 7.5)


def test_findings_queryable_by_case(entity_db):
    service = FactService(entity_db)
    assert [row["id"] for row in service.list_findings_by_case("D001", "C001")] == [
        "F001"
    ]
    assert [row["id"] for row in service.list_findings_by_case("D001", "C002")] == [
        "F002"
    ]


def test_findings_queryable_by_patient(entity_db):
    service = FactService(entity_db)
    assert [row["id"] for row in service.list_findings_by_patient("D001", "P001")] == [
        "F001",
        "F002",
    ]
    with pytest.raises(AccessDeniedError):
        service.list_findings_by_patient("D002", "P001")
