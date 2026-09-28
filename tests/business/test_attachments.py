"""Attachment ownership and zero-nodule analysis status."""

import pytest

from martin.db import connect, transaction
from martin.services.fact_service import FactService


def test_attachment_belongs_to_case(entity_db):
    service = FactService(entity_db)
    attachment_id = service.add_attachment(
        "D001", "C001", "scan.nii.gz", "ct/synthetic-scan.nii.gz"
    )
    assert service.add_attachment(
        "D001", "C001", "scan.nii.gz", "ct/synthetic-scan.nii.gz"
    ) == attachment_id
    with pytest.raises(ValueError, match="does not belong"):
        service.add_finding(
            "D001",
            "C002",
            "nodule",
            "2026-09-28",
            source_attachment_id=attachment_id,
        )
    with connect(entity_db) as connection:
        assert connection.execute(
            "SELECT case_id FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()[0] == "C001"


def test_detection_without_nodules_marks_analyzed(entity_db):
    service = FactService(entity_db)
    attachment_id = service.add_attachment(
        "D001", "C001", "clear.nii.gz", "ct/clear.nii.gz"
    )
    with connect(entity_db) as connection:
        before = connection.execute("SELECT count(*) FROM findings").fetchone()[0]
    with transaction(entity_db) as connection:
        from martin.repositories.threads import ThreadRepository

        thread_id = ThreadRepository(connection).create("D001", "C001")
    assert service.record_analysis("D001", thread_id, "ct/clear.nii.gz", []) == []
    with connect(entity_db) as connection:
        assert connection.execute(
            "SELECT analyzed_at FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()[0]
        assert connection.execute("SELECT count(*) FROM findings").fetchone()[0] == before
