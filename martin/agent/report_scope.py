"""Server-only report scope, isolated per Agent/API invocation."""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportScope:
    doctor_id: str
    thread_id: str


_report_scope: ContextVar[ReportScope | None] = ContextVar(
    "report_scope", default=None
)


def current_report_scope() -> ReportScope | None:
    return _report_scope.get()


def set_report_scope(doctor_id: str | None, thread_id: str | None):
    scope = ReportScope(doctor_id, thread_id) if doctor_id and thread_id else None
    return _report_scope.set(scope)


def reset_report_scope(token) -> None:
    _report_scope.reset(token)
