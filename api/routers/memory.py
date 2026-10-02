"""Authenticated, explicit writes for cross-thread doctor preferences."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps.auth import get_current_doctor
from martin.auth.session_service import DoctorIdentity
from martin.memory.models import MemoryCandidate
from martin.memory.router import MemoryRetrievalRouter
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.memory.writer import MemoryWriter
from martin.services.access_service import AccessDeniedError, EntityNotFoundError


router = APIRouter(prefix="/memory", tags=["Memory"])


class ReportStylePreference(BaseModel):
    conclusion_first: bool = True
    max_words: int = Field(default=200, ge=50, le=1000)
    focus: list[str] = Field(default_factory=list, max_length=10)


@router.post("/preferences/report-style")
def save_report_style(
    preference: ReportStylePreference,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    try:
        MemoryService().save_doctor_preference(
            doctor.id, "report_style", preference.model_dump()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="偏好保存失败，请重试") from exc
    return {"status": "saved"}


@router.get("/preferences/report-style")
def get_report_style(doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return MemoryService().get_doctor_preferences(doctor.id).get("report_style", {})
    except Exception as exc:
        raise HTTPException(status_code=503, detail="偏好读取失败，请重试") from exc


class MemoryFragment(BaseModel):
    memory_type: Literal[
        "workflow_preference",
        "clinical_decision",
        "historical_discussion",
        "task_followup",
        "correction",
    ]
    text: str = Field(min_length=1, max_length=1200)
    logical_key: str | None = Field(default=None, min_length=1, max_length=120)
    observed_at: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class MemoryWriteRequest(BaseModel):
    candidates: list[MemoryFragment] = Field(min_length=1, max_length=20)


class MemoryRetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    patient_id: str | None = None
    case_id: str | None = None
    modes: list[Literal["exact", "temporal", "semantic"]] | None = None
    finding_type: str | None = None
    body_location: str | None = None
    observed_after: str | None = None
    observed_before: str | None = None
    source_finding_id: str | None = None
    lesion_id: str | None = None
    semantic_case_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


@router.get("/threads/{thread_id}/records")
def list_memory_records(
    thread_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path)
        return {"records": service.list_records(scope)}
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话记忆") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆读取失败，请重试") from exc


@router.post("/threads/{thread_id}/records")
def write_memory_records(
    thread_id: str, request: MemoryWriteRequest,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path, write=True)
        candidates = [
            MemoryCandidate(**fragment.model_dump()) for fragment in request.candidates
        ]
        result = MemoryWriter(service).write(
            scope, candidates, source_type="thread", source_id=thread_id,
            interaction_id=str(uuid4()),
        )
        return {
            "status": "saved", "records": result.records,
            "deduplicated": result.deduplicated,
            "index_available": result.index_available,
            "error_code": result.error_code,
        }
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权写入该会话记忆") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="长期记忆保存失败，请重试") from exc


@router.post("/threads/{thread_id}/retrieve")
def retrieve_memory(
    thread_id: str, request: MemoryRetrieveRequest,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    try:
        result = MemoryRetrievalRouter().retrieve(
            doctor.id, thread_id, **request.model_dump()
        )
        return result.to_dict()
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权检索该会话记忆") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆检索失败，请重试") from exc
