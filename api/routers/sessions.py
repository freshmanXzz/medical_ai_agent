"""Session 管理 API 路由

复用已有 SQLite session，不重新实现会话管理。
"""
import logging
from fastapi import APIRouter, HTTPException
from api.models import SessionSummary as PydSessionSummary, SessionListResponse, SessionDetailResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["会话管理"])


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions():
    """获取所有历史会话列表。"""
    from martin.agent.sessions import SessionManager, get_default_checkpointer
    
    checkpointer = get_default_checkpointer()
    manager = SessionManager(checkpointer)
    summaries = manager.list_sessions()
    
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
def get_session_detail(thread_id: str):
    """获取指定会话的详细信息（消息历史 + 病例上下文）。"""
    from martin.agent.sessions import SessionManager, get_default_checkpointer
    
    checkpointer = get_default_checkpointer()
    manager = SessionManager(checkpointer)
    
    messages = manager.get_messages(thread_id)
    if not messages and thread_id != "default":
        raise HTTPException(status_code=404, detail=f"会话 {thread_id} 不存在")
    
    # 从 Checkpointer state 读取病例上下文
    case_context = manager.get_case_context(thread_id)
    
    return SessionDetailResponse(
        thread_id=thread_id,
        title=messages[0].content[:48] if messages else "未命名会话",
        messages=[{"role": m.role, "content": m.content} for m in messages],
        case_context=case_context,
    )
