"""报告生成 API 路由

封装已有 generate_report() 工具，不重新实现报告生成逻辑。
"""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps.auth import get_current_doctor, require_thread_access
from api.models import ReportRequest, ReportResponse
from api.routers.budget import record_budget_trace
from martin.auth.session_service import DoctorIdentity
from martin.llm.context_budget import begin_budget_scope, finish_budget_scope
from martin.services.access_service import AccessDeniedError, EntityNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["报告生成"])


@router.post("/report/generate", response_model=ReportResponse)
def generate_case_report(
    request: ReportRequest, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    """按授权会话读取业务 Finding 和已保存上下文，再调用报告工具。"""
    from martin.agent.case_context import CaseContext
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.agent.sessions import SessionManager, get_default_checkpointer
    from martin.agent.tools import generate_report, reset_case_context, set_case_context

    try:
        require_thread_access(doctor, request.session_id)
        saved = SessionManager(get_default_checkpointer()).get_case_context(
            request.session_id
        )
        context_token = set_case_context(CaseContext.from_dict(saved))
        scope_token = set_report_scope(doctor.id, request.session_id)
        budget_token = begin_budget_scope(
            "report", doctor_id=doctor.id, thread_id=request.session_id
        )
        try:
            report = generate_report.invoke(
                {"report_type": request.report_type, "language": request.language}
            )
        finally:
            trace = finish_budget_scope(budget_token)
            record_budget_trace(doctor.id, request.session_id, trace)
            reset_report_scope(scope_token)
            reset_case_context(context_token)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话") from exc
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    except sqlite3.Error as exc:
        logger.warning("报告所需的当前病例事实不可用: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="当前病例事实不可用，请稍后重试。") from exc
    
    if report.startswith("报告生成失败") or report.startswith("错误"):
        raise HTTPException(status_code=500, detail=report)
    
    return ReportResponse(
        report=report,
        report_type=request.report_type,
        language=request.language,
    )
