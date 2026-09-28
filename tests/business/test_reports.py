"""Reports retain each case version."""

from martin.services.fact_service import FactService


def test_report_versions_are_preserved(entity_db):
    service = FactService(entity_db)
    first = service.add_report("D001", "C001", "Synthetic report v1")
    second = service.add_report("D001", "C001", "Synthetic report v2")
    rows = service.list_reports_by_case("D001", "C001")
    assert [(row["id"], row["version"], row["content"]) for row in rows] == [
        (first, 1, "Synthetic report v1"),
        (second, 2, "Synthetic report v2"),
    ]
