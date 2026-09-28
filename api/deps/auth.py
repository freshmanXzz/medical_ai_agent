"""Resolve the current doctor from the server-side session cookie."""

from fastapi import Cookie, HTTPException, status

from martin.auth.session_service import DoctorIdentity, SessionService
from martin.services.access_service import AccessDeniedError, EntityNotFoundError
from martin.services.thread_service import ThreadService


COOKIE_NAME = "martin_session"


def get_current_doctor(
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> DoctorIdentity:
    doctor = SessionService().authenticate(token)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return doctor


def require_thread_access(
    doctor: DoctorIdentity, thread_id: str, *, write: bool = False
) -> dict:
    try:
        return ThreadService().get_thread_authorized(doctor.id, thread_id, write=write)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话") from exc
