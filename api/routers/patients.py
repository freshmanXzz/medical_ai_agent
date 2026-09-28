"""Actor-scoped patient reads."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps.auth import get_current_doctor
from martin.auth.session_service import DoctorIdentity
from martin.services.access_service import AccessDeniedError, EntityNotFoundError
from martin.services.case_service import CaseService
from martin.services.fact_service import FactService


router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/{patient_id}")
def get_patient(patient_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return CaseService().get_patient_authorized(doctor.id, patient_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="患者不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者") from exc


@router.get("/{patient_id}/cases")
def list_patient_cases(patient_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return CaseService().list_cases_for_patient_authorized(doctor.id, patient_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="患者不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者") from exc


@router.get("/{patient_id}/findings")
def list_patient_findings(
    patient_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    try:
        return FactService().list_findings_by_patient(doctor.id, patient_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="患者不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者") from exc
