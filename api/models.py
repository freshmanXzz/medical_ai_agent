"""Pydantic 请求/响应数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ─── Agent 对话 ────────────────────────────────────────────

class AttachmentInfo(BaseModel):
    """附件信息模型"""
    object_key: str = Field(..., description="OSS 对象路径")
    filename: str = Field(..., description="原始文件名")
    medical_image: bool = Field(default=False, description="是否为医学影像文件")


class ChatRequest(BaseModel):
    """Agent 对话请求"""
    session_id: str = Field(default="default", description="会话 ID")
    user_message: str = Field(..., min_length=1, description="用户消息")
    case_context: Dict[str, Any] = Field(default_factory=dict, description="当前病例上下文")
    attachment: Optional[AttachmentInfo] = Field(default=None, description="附件信息")


class ToolCallInfo(BaseModel):
    """工具调用信息"""
    tool_name: str
    tool_args: Dict[str, Any]
    output: str


class ChatResponse(BaseModel):
    """Agent 对话响应"""
    output: str
    session_id: str
    tool_calls: List[ToolCallInfo] = Field(default_factory=list)
    case_context: Dict[str, Any] = Field(default_factory=dict)


# ─── 影像检测 ───────────────────────────────────────────────

class DetectRequest(BaseModel):
    """CT 影像检测请求"""
    image_path: str = Field(..., description="CT 图像文件路径")
    session_id: str = Field(default="default", description="关联的会话 ID")


class NoduleInfo(BaseModel):
    """结节信息"""
    index: int
    diameter: float
    score: float
    center: Dict[str, float] = Field(default_factory=dict)
    dimensions: Dict[str, float] = Field(default_factory=dict)


class DetectResponse(BaseModel):
    """CT 影像检测响应"""
    image: str
    total_nodules: int
    nodules: List[NoduleInfo] = Field(default_factory=list)
    raw_text: str = Field(default="", description="格式化文本结果")
    case_context: Dict[str, Any] = Field(default_factory=dict, description="病例上下文")


class UploadResponse(BaseModel):
    """影像文件上传响应"""
    object_name: str = Field(description="OSS 对象名")
    bucket: str = Field(description="存储 bucket 名称")
    size: int = Field(description="文件大小（字节）")


# ─── 知识库 ────────────────────────────────────────────────

class KnowledgeDocumentResponse(BaseModel):
    """知识库原文档响应"""
    filename: str = Field(..., description="文档文件名")
    content: str = Field(..., description="Markdown 原文内容")


# ── 报告生成 ───────────────────────────────────────────────

class ReportRequest(BaseModel):
    """报告生成请求"""
    detection_result: Dict[str, Any] = Field(..., description="检测结果字典")
    report_type: str = Field(default="detailed", description="报告类型: brief/detailed/research")
    language: str = Field(default="zh", description="报告语言: zh/en")
    case_context: Dict[str, Any] = Field(default_factory=dict, description="病例上下文")


class ReportResponse(BaseModel):
    """报告生成响应"""
    report: str
    report_type: str
    language: str


# ─── Session 管理 ───────────────────────────────────────────

class SessionSummary(BaseModel):
    """会话摘要"""
    thread_id: str
    title: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionSummary]
    total: int


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    thread_id: str
    title: str
    messages: List[Dict[str, str]]
    case_context: Dict[str, Any] = Field(default_factory=dict)


# ─── WebSocket 消息 ────────────────────────────────────────

class WsStatusMessage(BaseModel):
    """WebSocket 工作状态消息"""
    type: str = Field(description="消息类型: status/tool_call/observation/final/error/case_context")
    content: str = Field(description="消息内容")
    tool_name: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())
