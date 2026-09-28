"""Server-created business thread endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps.auth import get_current_doctor
from martin.auth.session_service import DoctorIdentity
from martin.services.access_service import AccessDeniedError, EntityNotFoundError
from martin.services.thread_service import ThreadService


router = APIRouter(prefix="/threads", tags=["Threads"])


class ThreadCreateRequest(BaseModel):
    case_id: str


@router.post("")
def create_thread(request: ThreadCreateRequest, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        thread_id = ThreadService().create_thread(doctor.id, request.case_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="病例不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该病例") from exc
    return {"thread_id": thread_id, "case_id": request.case_id}


@router.get("/{thread_id}")
def get_thread(thread_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return ThreadService().get_thread_authorized(doctor.id, thread_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话") from exc
