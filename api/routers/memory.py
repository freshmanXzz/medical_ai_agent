"""Authenticated memory submissions and authorized lifecycle management."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

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
    model_config = ConfigDict(extra="ignore")

    conclusion_first: bool = True
    max_words: int | None = Field(default=200, ge=50, le=1000)
    complex_case_unlimited: bool = False
    focus: list[str] = Field(default_factory=list, max_length=10)


def _submission_provenance(doctor: DoctorIdentity, thread_id: str | None = None):
    """An HTTP submission is not evidence of a stored conversation message."""
    return {
        "kind": "api_submission",
        "actor_role": "doctor",
        "actor_id": doctor.id,
        "submission_id": str(uuid4()),
        "thread_id": thread_id,
        "message_id": None,
    }


@router.post("/preferences/report-style")
def save_report_style(
    preference: ReportStylePreference,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    try:
        record = MemoryService().save_doctor_preference(
            doctor.id,
            "report_style",
            preference.model_dump(),
            provenance=_submission_provenance(doctor),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="偏好保存失败，请重试") from exc
    return {"status": "saved", "record": record}


@router.get("/preferences/report-style")
def get_report_style(doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return MemoryService().get_doctor_preferences(doctor.id).get("report_style", {})
    except Exception as exc:
        raise HTTPException(status_code=503, detail="偏好读取失败，请重试") from exc


class MemoryFragment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_type: Literal[
        "workflow_preference",
        "clinical_decision",
        "historical_discussion",
        "task_followup",
        "correction",
        "clinical_claim",
    ]
    text: str = Field(min_length=1, max_length=1200)
    logical_key: str | None = Field(default=None, min_length=1, max_length=120)
    observed_at: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    data: dict = Field(default_factory=dict)
    valid_until: str | None = None


class MemoryWriteRequest(BaseModel):
    # Preserve the existing contract: client-supplied scope/source coordinates
    # are ignored; authentication and the authorized thread determine them.
    model_config = ConfigDict(extra="ignore")

    candidates: list[MemoryFragment] = Field(min_length=1, max_length=20)


class MemoryRetractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=400)


class MemoryRevisionRequest(MemoryRetractionRequest):
    candidate: MemoryFragment


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
    thread_id: str,
    include_inactive: bool = False,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path)
        return {
            "records": service.list_records(scope, include_inactive=include_inactive)
        }
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话记忆") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆读取失败，请重试") from exc


@router.post("/threads/{thread_id}/records")
def write_memory_records(
    thread_id: str, request: MemoryWriteRequest,
    background_tasks: BackgroundTasks,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path, write=True)
        candidates = [
            MemoryCandidate(**fragment.model_dump()) for fragment in request.candidates
        ]
        result = MemoryWriter(service).write(
            scope,
            candidates,
            source_type="thread",
            source_id=thread_id,
            provenance=_submission_provenance(doctor, thread_id),
        )
        if result.governance_job and result.governance_job.get("queued"):
            from martin.memory.governance_jobs import process_pending

            background_tasks.add_task(process_pending, doctor.id, thread_id)
        return {
            "status": "saved", "records": result.records,
            "deduplicated": result.deduplicated,
            "index_available": result.index_available,
            "error_code": result.error_code,
            "decisions": result.decisions,
            "governance_job": result.governance_job,
        }
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权写入该会话记忆") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="长期记忆保存失败，请重试") from exc


@router.get("/threads/{thread_id}/records/{memory_id}/history")
def get_memory_history(
    thread_id: str,
    memory_id: str,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path)
        if service.get_record(scope, memory_id, include_inactive=True) is None:
            raise HTTPException(status_code=404, detail="记忆不存在或不可访问")
        return {"records": service.record_history(scope, memory_id)}
    except HTTPException:
        raise
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话记忆") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆历史读取失败，请重试") from exc


@router.post("/threads/{thread_id}/records/{memory_id}/retract")
def retract_memory_record(
    thread_id: str,
    memory_id: str,
    request: MemoryRetractionRequest,
    background_tasks: BackgroundTasks,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path, write=True)
        if service.get_record(scope, memory_id, include_inactive=True) is None:
            raise HTTPException(status_code=404, detail="记忆不存在或不可访问")
        record = service.retract_record(
            scope,
            memory_id,
            reason=request.reason,
            provenance=_submission_provenance(doctor, thread_id),
        )
        from martin.memory.governance_jobs import process_pending

        background_tasks.add_task(process_pending, doctor.id, thread_id)
        return {"status": "retracted", "record": record}
    except HTTPException:
        raise
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权修改该会话记忆") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆撤回失败，请重试") from exc


@router.post("/threads/{thread_id}/records/{memory_id}/revise")
def revise_memory_record(
    thread_id: str,
    memory_id: str,
    request: MemoryRevisionRequest,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    service = MemoryService()
    try:
        scope = authorize_scope(doctor.id, thread_id, service.db_path, write=True)
        if service.get_record(scope, memory_id, include_inactive=True) is None:
            raise HTTPException(status_code=404, detail="记忆不存在或不可访问")
        result = MemoryWriter(service).revise(
            scope,
            memory_id,
            MemoryCandidate(**request.candidate.model_dump()),
            reason=request.reason,
            provenance=_submission_provenance(doctor, thread_id),
        )
        return {
            "status": "saved",
            "records": result.records,
            "deduplicated": result.deduplicated,
            "index_available": result.index_available,
            "error_code": result.error_code,
        }
    except HTTPException:
        raise
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权修改该会话记忆") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆修订失败，请重试") from exc


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
