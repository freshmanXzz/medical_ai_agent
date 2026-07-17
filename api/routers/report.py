"""报告生成 API 路由

封装已有 generate_report() 工具，不重新实现报告生成逻辑。
"""
import json
import logging
from fastapi import APIRouter, HTTPException
from api.models import ReportRequest, ReportResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["报告生成"])


@router.post("/report/generate", response_model=ReportResponse)
def generate_case_report(request: ReportRequest):
    """调用已有 generate_report 工具生成 Markdown 报告。"""
    from martin.agent.tools import generate_report
    
    detection_json = json.dumps(request.detection_result, ensure_ascii=False)
    case_context_json = json.dumps(request.case_context, ensure_ascii=False)
    
    report = generate_report.invoke({
        "detection_result": detection_json,
        "report_type": request.report_type,
        "language": request.language,
        "case_context": case_context_json,
    })
    
    if report.startswith("报告生成失败") or report.startswith("错误"):
        raise HTTPException(status_code=500, detail=report)
    
    return ReportResponse(
        report=report,
        report_type=request.report_type,
        language=request.language,
    )
