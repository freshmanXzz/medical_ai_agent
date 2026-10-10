"""Authorized retrieval of discussion and decision memories."""

from __future__ import annotations

import math
import re

from martin.services.access_service import AccessDeniedError, EntityNotFoundError

from .models import normalize_time
from .vector_index import SEMANTIC_MEMORY_TYPES, get_default_vector_index


def _utc_time(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_time(value)


def _terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", text.lower()))
    for phrase in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return terms


class SemanticRetriever:
    def __init__(self, service, index=None, *, minimum_score: float = 0.45):
        self.service = service
        self.index = index
        self.minimum_score = minimum_score

    def _authorize(self, scope):
        from .scope import revalidate_scope

        return revalidate_scope(scope, db_path=self.service.db_path)

    def _valid(self, scope, record, memory_types) -> bool:
        from .lifecycle import is_record_active

        return bool(
            record
            and record.get("doctor_id") == scope.doctor_id
            and record.get("patient_id") == scope.patient_id
            and is_record_active(record)
            and record.get("memory_type") in memory_types
            and isinstance(record.get("text"), str)
            and record["text"].strip()
            and self.service.validate_record_source(scope, record)
        )

    def _reserved_paths(self):
        paths = [self.service.db_path] if self.service.db_path else []
        source_store = self.service.store
        connection = getattr(source_store, "conn", None)
        if connection is not None:
            paths.extend(
                row[2] for row in connection.execute("PRAGMA database_list") if row[2]
            )
        return paths

    def retrieve(
        self, scope, query: str, *, limit: int = 5, case_id=None,
        observed_after=None, observed_before=None, memory_types=None,
    ) -> dict:
        self._authorize(scope)
        if not scope.patient_id or not isinstance(query, str) or not query.strip():
            return {"records": [], "available": True, "error_code": None}
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Semantic retrieval limit must be between 1 and 100")
        requested_types = tuple(
            memory_types or ("clinical_decision", "historical_discussion")
        )
        if any(kind not in SEMANTIC_MEMORY_TYPES for kind in requested_types):
            raise ValueError("Unsupported semantic memory type")
        after, before = _utc_time(observed_after), _utc_time(observed_before)
        if after and before and after > before:
            raise ValueError("Semantic time range is reversed")
        # Sync every valid semantic record, even when this query selects one type.
        try:
            records = [
                record for record in self.service.list_records(scope)
                if self._valid(scope, record, SEMANTIC_MEMORY_TYPES)
            ]
            reserved = self._reserved_paths()
        except (AccessDeniedError, EntityNotFoundError):
            raise
        except Exception:
            return {
                "records": [], "available": False,
                "error_code": "memory_store_unavailable",
            }
        if not records:
            # No index/model is needed, and stale index rows cannot become evidence.
            self._authorize(scope)
            return {"records": [], "available": True, "error_code": None}
        try:
            index = (
                self.index if self.index is not None else get_default_vector_index()
            )
            index.sync(scope, records, reserved_paths=reserved)
            matches = index.search(
                scope, query, limit=min(limit * 4, 100), case_id=case_id,
                observed_after=after, observed_before=before,
                memory_types=requested_types,
            )
        except (AccessDeniedError, EntityNotFoundError):
            raise
        except Exception:
            return {
                "records": [], "available": False,
                "error_code": "semantic_index_unavailable",
            }
        results = []
        query_terms = _terms(query)
        try:
            for match in matches:
                score = float(match["score"])
                if not math.isfinite(score) or score < self.minimum_score:
                    continue
                record = self.service.get_record(scope, match["memory_id"])
                if not self._valid(scope, record, requested_types):
                    continue
                if case_id is not None and record.get("case_id") != case_id:
                    continue
                observed = _utc_time(record.get("observed_at"))
                if (after or before) and not observed:
                    continue
                if (after and observed < after) or (before and observed > before):
                    continue
                overlap = len(query_terms & _terms(record["text"])) / max(
                    1, len(query_terms)
                )
                results.append({
                    **record, "retrieval_method": "semantic", "score": score,
                    "relevance_score": score + 0.05 * overlap,
                })
            self._authorize(scope)
        except (AccessDeniedError, EntityNotFoundError):
            raise
        except Exception:
            return {
                "records": [], "available": False,
                "error_code": "memory_store_unavailable",
            }
        results.sort(key=lambda item: (-item["relevance_score"], item["memory_id"]))
        unique = {record["memory_id"]: record for record in reversed(results)}
        ranked = sorted(
            unique.values(),
            key=lambda item: (-item["relevance_score"], item["memory_id"]),
        )
        return {"records": ranked[:limit], "available": True, "error_code": None}
