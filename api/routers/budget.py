"""Authenticated budget policy and private trace endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api.deps.auth import get_current_doctor
from martin.auth.session_service import DoctorIdentity
from martin.memory.budget_policy import PolicyService, PolicyVersionConflict
from martin.memory.scope import authorize_scope
from martin.services.access_service import AccessDeniedError, EntityNotFoundError

router = APIRouter(prefix="/memory/budget", tags=["Memory budget"])
logger = logging.getLogger(__name__)


def record_budget_trace(doctor_id, thread_id, trace):
    """Persist references and metrics after fresh business authorization."""
    if not isinstance(trace, dict) or not trace:
        return
    try:
        service = PolicyService()
        scope = authorize_scope(doctor_id, thread_id, service.db_path)
        service.record_trace(scope, trace)
    except Exception as exc:
        # Telemetry failure must not replace a validated public answer.
        logger.warning("预算使用记录未保存: %s", type(exc).__name__)


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)
    policy: dict
    reason: str = Field(default="", max_length=500)


class PolicyRollback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)
    target_version: StrictInt = Field(ge=0)
    reason: str = Field(default="", max_length=500)


def _public_info(service, doctor):
    return dict(service.current_info(), can_manage=service.can_manage(doctor.id))


@router.get("/policy")
def get_policy(doctor: DoctorIdentity = Depends(get_current_doctor)):
    return _public_info(PolicyService(), doctor)


@router.put("/policy")
def save_policy(
    request: PolicyUpdate, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    service = PolicyService()
    try:
        service.save(
            doctor.id,
            request.policy,
            expected_version=request.expected_version,
            reason=request.reason,
        )
        return _public_info(service, doctor)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="需要预算管理员权限") from exc
    except PolicyVersionConflict as exc:
        raise HTTPException(
            status_code=409, detail="预算策略已变更，请刷新后重试"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="预算策略未保存，请重试") from exc


@router.get("/history")
def policy_history(doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return {"versions": PolicyService().versions(doctor.id)}
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="需要预算管理员权限") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="预算策略历史暂不可用") from exc


@router.post("/rollback")
def rollback_policy(
    request: PolicyRollback, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    service = PolicyService()
    try:
        service.rollback(
            doctor.id,
            request.target_version,
            expected_version=request.expected_version,
            reason=request.reason,
        )
        return _public_info(service, doctor)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="需要预算管理员权限") from exc
    except PolicyVersionConflict as exc:
        raise HTTPException(
            status_code=409, detail="预算策略已变更，请刷新后重试"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="预算策略未回退，请重试") from exc


@router.get("/trace")
def get_trace(thread_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        service = PolicyService()
        scope = authorize_scope(doctor.id, thread_id, service.db_path)
        return {"trace": service.latest_trace(scope)}
    except (AccessDeniedError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话的预算记录") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="预算使用记录暂不可用") from exc
