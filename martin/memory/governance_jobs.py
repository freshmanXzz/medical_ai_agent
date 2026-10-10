"""Durable, bounded summary jobs runnable by a scheduler or an explicit CLI."""

import argparse
import logging

from martin.services.access_service import AccessDeniedError, EntityNotFoundError

from .lifecycle import write_lock
from .models import normalize_time
from .scope import authorize_scope, revalidate_scope
from .summaries import SummaryService, _counter, fingerprint, summaries_ns

logger = logging.getLogger(__name__)


def _jobs_ns(scope):
    namespace = summaries_ns(scope)
    return (*namespace[:-1], "summary_jobs")


class GovernanceJobs:
    """Persist work before processing; no stable external worker is assumed."""

    def __init__(self, service):
        self.service = service
        self.summaries = SummaryService(service)

    def enqueue(
        self,
        scope,
        *,
        min_sources,
        min_tokens,
        token_counter,
        force=False,
        policy_version=None,
    ):
        if (
            type(min_sources) is not int
            or min_sources < 1
            or type(min_tokens) is not int
            or min_tokens < 1
        ):
            raise ValueError("Summary triggers must be positive integers")
        with write_lock:
            revalidate_scope(scope, db_path=self.service.db_path)
            records = self.summaries.eligible_sources(scope)
            tokens = _counter(
                token_counter, "\n".join(record["text"] for record in records)
            )
            head = self.service._store().get(
                summaries_ns(scope), "head:" + scope.case_id
            )
            if head and isinstance(head.value, dict):
                current = self.service._store().get(
                    summaries_ns(scope), head.value.get("summary_id", "")
                )
                if current is None or not self.summaries._valid_summary(
                    scope, current.value
                ):
                    force = True
            if not records or (
                not force and len(records) < min_sources and tokens < min_tokens
            ):
                return {
                    "queued": False,
                    "status": "below_threshold",
                    "source_count": len(records),
                    "estimated_tokens": tokens,
                    "job_id": None,
                }
            source_version = self.summaries.source_version(records)
            job_id = (
                "job:"
                + scope.case_id
                + ":"
                + fingerprint([source_version, policy_version])
            )
            namespace = _jobs_ns(scope)
            existing = self.service._store().get(namespace, job_id)
            if existing:
                return {
                    "queued": existing.value["status"] in ("queued", "running"),
                    "status": existing.value["status"],
                    "job_id": job_id,
                    "source_count": len(records),
                    "estimated_tokens": tokens,
                }
            job = {
                "kind": "summary_job",
                "job_id": job_id,
                "doctor_id": scope.doctor_id,
                "patient_id": scope.patient_id,
                "case_id": scope.case_id,
                "thread_id": scope.thread_id,
                "source_version": source_version,
                "policy_version": policy_version,
                "status": "queued",
                "attempts": 0,
                "source_count": len(records),
                "estimated_tokens": tokens,
                "created_at": normalize_time(None),
                "updated_at": normalize_time(None),
            }
            revalidate_scope(scope, db_path=self.service.db_path)
            self.service._store().put(namespace, job_id, job)
            return {
                "queued": True,
                "status": "queued",
                "job_id": job_id,
                "source_count": len(records),
                "estimated_tokens": tokens,
            }

    def list_jobs(self, scope):
        revalidate_scope(scope, db_path=self.service.db_path)
        rows, offset = [], 0
        while True:
            page = self.service._store().search(
                _jobs_ns(scope), limit=100, offset=offset
            )
            for item in page:
                job = item.value
                if (
                    isinstance(job, dict)
                    and job.get("kind") == "summary_job"
                    and item.key == job.get("job_id")
                    and all(
                        job.get(key) == getattr(scope, key)
                        for key in ("doctor_id", "patient_id", "case_id")
                    )
                ):
                    rows.append(job)
            if len(page) < 100:
                break
            offset += len(page)
        revalidate_scope(scope, db_path=self.service.db_path)
        return sorted(rows, key=lambda job: (job["created_at"], job["job_id"]))

    def run(
        self, scope, *, max_jobs, max_attempts, summary_token_budget, token_counter
    ):
        if (
            type(max_jobs) is not int
            or not 1 <= max_jobs <= 100
            or type(max_attempts) is not int
            or not 1 <= max_attempts <= 10
        ):
            raise ValueError("Summary processing must have bounded jobs and attempts")
        results = []
        # Claim/version checks and publication share the lifecycle lock. A crash
        # leaves running work durable and recoverable, consuming one attempt.
        with write_lock:
            revalidate_scope(scope, db_path=self.service.db_path)
            jobs = [
                job
                for job in self.list_jobs(scope)
                if job["status"] in ("queued", "running")
            ]
            for snapshot in jobs[:max_jobs]:
                namespace = _jobs_ns(scope)
                latest = self.service._store().get(namespace, snapshot["job_id"])
                if not latest or latest.value != snapshot:
                    results.append(
                        {"job_id": snapshot["job_id"], "status": "cas_conflict"}
                    )
                    continue
                if snapshot.get("attempts", 0) >= max_attempts:
                    failed = dict(
                        snapshot,
                        status="failed",
                        error_code="retry_limit",
                        updated_at=normalize_time(None),
                    )
                    self.service._store().put(namespace, snapshot["job_id"], failed)
                    results.append(
                        {
                            "job_id": snapshot["job_id"],
                            "status": "failed",
                            "error_code": "retry_limit",
                        }
                    )
                    continue
                running = dict(
                    snapshot,
                    status="running",
                    attempts=snapshot["attempts"] + 1,
                    updated_at=normalize_time(None),
                )
                self.service._store().put(namespace, snapshot["job_id"], running)
                try:

                    def publication_guard():
                        claimed = self.service._store().get(
                            namespace, snapshot["job_id"]
                        )
                        return claimed is not None and claimed.value == running

                    payload = self.summaries.rebuild(
                        scope,
                        token_budget=summary_token_budget,
                        token_counter=token_counter,
                        expected_source_version=running["source_version"],
                        policy_version=running.get("policy_version"),
                        publication_guard=publication_guard,
                    )
                    if payload["available"]:
                        completed = dict(
                            running,
                            status="completed",
                            summary_id=payload["summary_id"],
                            updated_at=normalize_time(None),
                            error_code=None,
                        )
                    else:
                        reason = payload["error_code"]
                        state = (
                            "obsolete"
                            if reason == "source_changed"
                            else (
                                "failed"
                                if running["attempts"] >= max_attempts
                                else "queued"
                            )
                        )
                        completed = dict(
                            running,
                            status=state,
                            error_code=reason,
                            updated_at=normalize_time(None),
                        )
                except (AccessDeniedError, EntityNotFoundError):
                    raise
                except Exception:
                    completed = dict(
                        running,
                        status=(
                            "failed"
                            if running["attempts"] >= max_attempts
                            else "queued"
                        ),
                        error_code="summary_job_failed",
                        updated_at=normalize_time(None),
                    )
                # Do not let an intervening cancellation or another claimant's
                # result be overwritten. This is process-local CAS, not a claim
                # of multi-worker serializability.
                current = self.service._store().get(namespace, snapshot["job_id"])
                if current is None or current.value != running:
                    results.append(
                        {"job_id": snapshot["job_id"], "status": "cas_conflict"}
                    )
                    continue
                revalidate_scope(scope, db_path=self.service.db_path)
                self.service._store().put(namespace, snapshot["job_id"], completed)
                results.append(
                    {
                        key: completed.get(key)
                        for key in (
                            "job_id",
                            "status",
                            "attempts",
                            "summary_id",
                            "error_code",
                        )
                    }
                )
        return results

    def periodic(
        self,
        scopes,
        *,
        min_sources,
        min_tokens,
        token_counter,
        summary_token_budget,
        max_jobs,
        max_attempts,
        policy_version=None,
    ):
        """One bounded low-priority sweep; deployment chooses when to call it."""
        results = []
        for scope in scopes:
            queued = self.enqueue(
                scope,
                min_sources=min_sources,
                min_tokens=min_tokens,
                token_counter=token_counter,
                policy_version=policy_version,
            )
            results.append(
                {
                    "scope": {
                        key: getattr(scope, key)
                        for key in ("doctor_id", "patient_id", "case_id")
                    },
                    "enqueue": queued,
                    "jobs": self.run(
                        scope,
                        max_jobs=max_jobs,
                        max_attempts=max_attempts,
                        summary_token_budget=summary_token_budget,
                        token_counter=token_counter,
                    ),
                }
            )
        return results


def enqueue_from_policy(service, scope, *, force=False) -> dict:
    """Share effective trigger configuration across writers and retractions."""
    from .budget_policy import PolicyService

    try:
        policy = PolicyService(service.db_path, store=service._store()).current()
        return GovernanceJobs(service).enqueue(
            scope,
            min_sources=policy.summary_trigger_count,
            min_tokens=policy.summary_trigger_tokens,
            token_counter=lambda text: len(text.encode("utf-8")),
            policy_version=policy.version,
            force=force,
        )
    except Exception as exc:
        logger.warning("Summary queue unavailable: %s", type(exc).__name__)
        return {"queued": False, "error_code": "summary_queue_unavailable"}


def process_pending(doctor_id: str, thread_id: str) -> list[dict]:
    """Background entry; always resolve authorization and policy afresh."""
    from .budget_policy import PolicyService
    from .service import MemoryService

    try:
        service = MemoryService()
        scope = authorize_scope(doctor_id, thread_id, service.db_path)
        policy = PolicyService(service.db_path, store=service._store()).current()
        return GovernanceJobs(service).run(
            scope,
            max_jobs=4,
            max_attempts=3,
            summary_token_budget=policy.summary_tokens,
            token_counter=lambda text: len(text.encode("utf-8")),
        )
    except Exception as exc:
        logger.warning("Summary governance unavailable: %s", type(exc).__name__)
        return [
            {"status": "unavailable", "error_code": "summary_governance_unavailable"}
        ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor-id", required=True)
    parser.add_argument("--thread-id", action="append", required=True)
    parser.add_argument("--min-sources", type=int, required=True)
    parser.add_argument("--trigger-tokens", type=int, required=True)
    parser.add_argument("--summary-tokens", type=int, required=True)
    parser.add_argument("--max-jobs", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    from .service import MemoryService

    service = MemoryService()
    scopes = [
        authorize_scope(args.doctor_id, thread, service.db_path)
        for thread in args.thread_id
    ]
    results = GovernanceJobs(service).periodic(
        scopes,
        min_sources=args.min_sources,
        min_tokens=args.trigger_tokens,
        summary_token_budget=args.summary_tokens,
        max_jobs=args.max_jobs,
        max_attempts=args.max_attempts,
        token_counter=lambda text: len(text.encode("utf-8")),
    )
    # No source text is sent to operational stdout.
    import json

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
