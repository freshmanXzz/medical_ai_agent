"""Authenticated, explicit writes for cross-thread doctor preferences."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps.auth import get_current_doctor
from martin.auth.session_service import DoctorIdentity
from martin.memory.service import MemoryService


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
