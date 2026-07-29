"""Pydantic 请求/响应数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ─── Agent 对话 ────────────────────────────────────────────

class AttachmentInfo(BaseModel):
    """仅用于对话展示的附件元数据，不携带存储对象引用。"""
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
    size: int = Field(description="文件大小（字节）")
    filename: str = Field(description="原始上传文件名")


class ViewerWindow(BaseModel):
    center: float
    width: float


class ViewerDisplayPoint(BaseModel):
    x: float
    y: float
    z: float


class ViewerDisplayBox(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


class ViewerNodule(BaseModel):
    index: Optional[int] = None
    diameter: Optional[float] = None
    score: Optional[float] = None
    spatial_status: str
    display_center: Optional[ViewerDisplayPoint] = None
    display_bbox: Optional[ViewerDisplayBox] = None


class ViewerManifestResponse(BaseModel):
    """不含路径或对象键的病例阅片元数据。"""

    shape: List[int]
    axial_slice_count: int
    default_window: ViewerWindow
    nodules: List[ViewerNodule] = Field(default_factory=list)


# ─── 知识库 ────────────────────────────────────────────────

class KnowledgeDocumentResponse(BaseModel):
    """知识库原文档响应"""
    filename: str = Field(..., description="文档文件名")
    content: str = Field(..., description="Markdown 原文内容")


class KnowledgeDocumentSummary(BaseModel):
    """知识库管理页中的单份资料摘要。"""
    document_id: str
    filename: str
    source_type: str
    status: str
    created_at: str = ""
    chunk_count: Optional[int] = None
    deletable: bool = False
    error: Optional[str] = None


class KnowledgeDocumentListResponse(BaseModel):
    documents: List[KnowledgeDocumentSummary]
    total: int


class KnowledgeRebuildResponse(BaseModel):
    documents: int
    chunks: int


class KnowledgeSearchRequest(BaseModel):
    """知识库原始向量检索请求。"""

    query: str = Field(..., description="用于向量召回的原始查询文本")


class KnowledgeSearchResult(BaseModel):
    """单个知识库向量召回结果。"""

    rank: int
    score: float
    source: str = ""
    source_type: str = ""
    document_id: str = ""
    content: str


class KnowledgeSearchResponse(BaseModel):
    """知识库原始向量检索响应。"""

    query: str
    results: List[KnowledgeSearchResult] = Field(default_factory=list)
    total: int


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
