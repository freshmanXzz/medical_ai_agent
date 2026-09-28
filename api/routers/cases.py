"""Actor-scoped case reads."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps.auth import get_current_doctor
from api.models import BusinessReportCreate, ClinicalContextUpdate, FindingCreate
from martin.auth.session_service import DoctorIdentity
from martin.services.access_service import AccessDeniedError, EntityNotFoundError
from martin.services.case_service import CaseService
from martin.services.thread_service import ThreadService
from martin.services.fact_service import FactService


router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get("/{case_id}")
def get_case(case_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return CaseService().get_case_authorized(doctor.id, case_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="病例不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该病例") from exc


@router.get("/{case_id}/threads")
def list_case_threads(case_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)):
    try:
        return ThreadService().list_by_case_authorized(doctor.id, case_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="病例不存在") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该病例") from exc


def _fact_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EntityNotFoundError):
        return HTTPException(status_code=404, detail="病例不存在")
    if isinstance(exc, AccessDeniedError):
        return HTTPException(status_code=403, detail="无权访问该病例")
    return HTTPException(status_code=400, detail=str(exc))


@router.patch("/{case_id}/clinical-context")
def update_clinical_context(
    case_id: str,
    update: ClinicalContextUpdate,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    try:
        return FactService().update_clinical_context(
            doctor.id, case_id, **update.model_dump(exclude_none=True)
        )
    except (EntityNotFoundError, AccessDeniedError, ValueError) as exc:
        raise _fact_error(exc) from exc


@router.post("/{case_id}/findings")
def add_finding(
    case_id: str,
    finding: FindingCreate,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    try:
        finding_id = FactService().add_finding(
            doctor.id, case_id, **finding.model_dump()
        )
    except (EntityNotFoundError, AccessDeniedError, ValueError) as exc:
        raise _fact_error(exc) from exc
    return {"finding_id": finding_id}


@router.get("/{case_id}/findings")
def list_case_findings(
    case_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    try:
        return FactService().list_findings_by_case(doctor.id, case_id)
    except (EntityNotFoundError, AccessDeniedError) as exc:
        raise _fact_error(exc) from exc


@router.get("/{case_id}/attachments")
def list_case_attachments(
    case_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    try:
        rows = FactService().list_attachments_by_case(doctor.id, case_id)
    except (EntityNotFoundError, AccessDeniedError) as exc:
        raise _fact_error(exc) from exc
    return [
        {
            "id": row["id"],
            "case_id": row["case_id"],
            "original_name": row["original_name"],
            "created_at": row["created_at"],
            "analyzed_at": row["analyzed_at"],
        }
        for row in rows
    ]


@router.post("/{case_id}/reports")
def add_report(
    case_id: str,
    report: BusinessReportCreate,
    doctor: DoctorIdentity = Depends(get_current_doctor),
):
    try:
        report_id = FactService().add_report(doctor.id, case_id, report.content)
    except (EntityNotFoundError, AccessDeniedError) as exc:
        raise _fact_error(exc) from exc
    return {"report_id": report_id}


@router.get("/{case_id}/reports")
def list_case_reports(
    case_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    try:
        return FactService().list_reports_by_case(doctor.id, case_id)
    except (EntityNotFoundError, AccessDeniedError) as exc:
        raise _fact_error(exc) from exc
