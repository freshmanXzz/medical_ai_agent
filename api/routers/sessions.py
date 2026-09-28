"""Session 管理 API 路由

复用已有 SQLite session，不重新实现会话管理。
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from api.models import SessionSummary as PydSessionSummary, SessionListResponse, SessionDetailResponse
from api.deps.auth import get_current_doctor, require_thread_access
from martin.auth.session_service import DoctorIdentity
from martin.services.thread_service import ThreadService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["会话管理"])


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(doctor: DoctorIdentity = Depends(get_current_doctor)):
    """只列出当前医生仍获授权的业务 Thread checkpoint。"""
    from martin.agent.sessions import SessionManager, get_default_checkpointer
    
    checkpointer = get_default_checkpointer()
    manager = SessionManager(checkpointer)
    authorized_ids = ThreadService().list_authorized_ids(doctor.id)
    summaries = [s for s in manager.list_sessions() if s.thread_id in authorized_ids]
    
    return SessionListResponse(
        sessions=[
            PydSessionSummary(
                thread_id=s.thread_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in summaries
        ],
        total=len(summaries),
    )


@router.get("/sessions/{thread_id}", response_model=SessionDetailResponse)
def get_session_detail(
    thread_id: str, doctor: DoctorIdentity = Depends(get_current_doctor)
):
    """获取指定会话的详细信息（消息历史 + 病例上下文）。"""
    require_thread_access(doctor, thread_id)
    from martin.agent.sessions import SessionManager, get_default_checkpointer
    
    checkpointer = get_default_checkpointer()
    manager = SessionManager(checkpointer)
    
    # 从 Checkpointer state 读取病例上下文
    case_context = manager.get_case_context(thread_id)
    messages = manager.get_messages(thread_id)
    if not messages and not case_context and thread_id != "default":
        raise HTTPException(status_code=404, detail=f"会话 {thread_id} 不存在")

    image_info = case_context.get("image_info", {}) if isinstance(case_context, dict) else {}
    fallback_title = (
        image_info.get("filename") or image_info.get("image_name", "")
        if isinstance(image_info, dict)
        else ""
    )
    
    from martin.agent.case_context import CaseContext

    public_context = CaseContext.from_dict(case_context).to_public_dict() if case_context else {}
    return SessionDetailResponse(
        thread_id=thread_id,
        title=messages[0].content[:48] if messages else (fallback_title or "未命名会话"),
        messages=[{"role": m.role, "content": m.content} for m in messages],
        case_context=public_context,
    )
