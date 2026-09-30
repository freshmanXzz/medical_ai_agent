"""Read current, authorized business Findings as report input.

This projection never reads the memory Store or writes business facts. Detector
fields belong to an individual Finding payload, so lists are never zipped with
model-supplied detections or historical patient observations.
"""

import json
from pathlib import Path

from martin.db import transaction
from martin.repositories.findings import FindingRepository
from martin.services.access_service import AccessService


class ReportInputService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def build(self, doctor_id: str, thread_id: str) -> dict | None:
        """Return current confirmed nodules, or None for legacy no-Finding cases.

        Authorization and fact reads share one transaction. Errors propagate:
        unavailable current-case facts must not silently become a detector-only
        report or an assertion that no nodule exists.
        """
        with transaction(self.db_path) as connection:
            thread = AccessService(connection).get_thread_authorized(
                doctor_id, thread_id
            )
            rows = FindingRepository(connection).list_by_case(thread["case_id"])
            nodules = []
            for row in rows:
                if row["status"] != "confirmed" or row["finding_type"] != "nodule":
                    continue
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                nodule = {
                    key: payload[key]
                    for key in ("score", "center", "dimensions")
                    if key in payload
                }
                # Business columns are authoritative, including missing values.
                nodule.update(
                    index=len(nodules) + 1,
                    finding_id=row["id"],
                    source_case_id=thread["case_id"],
                    anatomy=row["anatomy"],
                    observed_at=row["observed_at"],
                    diameter=row["diameter_mm"],
                )
                nodules.append(nodule)
            if not nodules:
                if not rows:
                    return None
                # An old checkpoint must not resurrect filtered business facts.
                return {
                    "image": thread["case_id"],
                    "source": "insufficient_data",
                    "source_case_id": thread["case_id"],
                    "detection_completed": False,
                    "total_nodules": 0,
                    "nodules": [],
                }
            return {
                "image": thread["case_id"],
                "source": "business_findings",
                "source_case_id": thread["case_id"],
                "detection_completed": False,
                "total_nodules": len(nodules),
                "nodules": nodules,
            }
