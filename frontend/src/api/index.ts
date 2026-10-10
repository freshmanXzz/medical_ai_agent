import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 900000,
  headers: { 'Content-Type': 'application/json' },
})

// Agent 对话
export const chatWithAgent = (
  sessionId: string,
  userMessage: string,
  caseContext: Record<string, unknown> = {}
) =>
  api.post('/agent/chat', {
    session_id: sessionId,
    user_message: userMessage,
    case_context: caseContext,
  })

// CT 影像文件上传到 OSS（multipart/form-data）
export function uploadImage(file: File, sessionId: string, onUploadProgress?: (progress: number) => void) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('session_id', sessionId)
  return api.post('/image/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
    onUploadProgress: (event) => {
      if (onUploadProgress && event.total) {
        onUploadProgress(Math.round((event.loaded * 100) / event.total))
      }
    },
  })
}

// CT 影像检测
export const analyzeImage = (sessionId: string) =>
  api.post('/image/analyze', {
    session_id: sessionId,
  })

// 报告生成
export const generateReport = (
  sessionId: string,
  detectionResult: Record<string, unknown>,
  reportType = 'detailed',
  language = 'zh',
  caseContext: Record<string, unknown> = {}
) =>
  api.post('/report/generate', {
    session_id: sessionId,
    detection_result: detectionResult,
    report_type: reportType,
    language,
    case_context: caseContext,
  })

// 会话列表
// 服务端创建会话 Thread（Entity V0：会话必须绑定病例且由服务端生成 ID）
export const createThread = (caseId: string) =>
  api.post<{ thread_id: string; case_id: string }>('/threads', { case_id: caseId })

export const listSessions = () => api.get('/sessions')

// 会话详情
export const getSessionDetail = (threadId: string) =>
  api.get(`/sessions/${encodeURIComponent(threadId)}`)

export interface ViewerWindow {
  center: number
  width: number
}

export interface ViewerDisplayPoint {
  x: number
  y: number
  z: number
}

export interface ViewerDisplayBox {
  x_min: number
  x_max: number
  y_min: number
  y_max: number
  z_min: number
  z_max: number
}

export interface ViewerNodule {
  index: number | null
  diameter?: number
  score?: number
  spatial_status: 'located' | 'unavailable' | 'outside_volume'
  display_center?: ViewerDisplayPoint
  display_bbox?: ViewerDisplayBox
}

export interface ViewerManifest {
  shape: [number, number, number]
  axial_slice_count: number
  default_window: ViewerWindow
  nodules: ViewerNodule[]
}

export const getViewerManifest = (threadId: string) =>
  api.get<ViewerManifest>(`/sessions/${encodeURIComponent(threadId)}/viewer/manifest`)

export function getViewerAxialSliceUrl(
  threadId: string,
  sliceIndex: number,
  windowCenter: number,
  windowWidth: number,
) {
  const query = new URLSearchParams({
    window_center: String(windowCenter),
    window_width: String(windowWidth),
  })
  return `/api/sessions/${encodeURIComponent(threadId)}/viewer/axial/${sliceIndex}.png?${query}`
}

// 知识库原文档查看
export const getKnowledgeDocument = (filename: string) =>
  api.get(`/knowledge/document/${encodeURIComponent(filename)}`)

export interface KnowledgeDocumentSummary {
  document_id: string
  filename: string
  source_type: 'builtin' | 'upload'
  status: 'ready' | 'indexing' | 'failed'
  created_at: string
  chunk_count: number | null
  deletable: boolean
  error?: string | null
}

export const listKnowledgeDocuments = () => api.get('/knowledge/documents')

export function uploadKnowledgeDocument(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/knowledge/documents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 900000,
  })
}

export const deleteKnowledgeDocument = (documentId: string) =>
  api.delete(`/knowledge/documents/${encodeURIComponent(documentId)}`)

export const rebuildKnowledgeBase = () => api.post('/knowledge/rebuild', {}, { timeout: 900000 })

export interface KnowledgeSearchResult {
  rank: number
  score: number
  source: string
  source_type: string
  document_id: string
  content: string
}

export interface KnowledgeSearchResponse {
  query: string
  results: KnowledgeSearchResult[]
  total: number
}

export const searchKnowledgeVectors = (query: string) =>
  api.post<KnowledgeSearchResponse>('/knowledge/search', { query })

// ---------- 认证 ----------
export interface DoctorInfo {
  id: string
  username: string
  display_name: string
}

export const loginDoctor = (username: string, password: string) =>
  api.post<DoctorInfo>('/auth/login', { username, password })

export const logoutDoctor = () => api.post('/auth/logout')

export const getCurrentDoctor = () => api.get<DoctorInfo>('/auth/me')

// ---------- 长期记忆治理 ----------
export type EditableMemoryType = 'workflow_preference' | 'clinical_decision' | 'historical_discussion' | 'task_followup' | 'correction' | 'clinical_claim'

export interface MemoryProvenance {
  kind: 'message' | 'api_submission' | 'business_event' | 'legacy_unknown'
  actor_id?: string | null
  message_id?: string | null
  submission_id?: string | null
  thread_id?: string | null
}

export interface MemoryRecord {
  memory_id: string
  memory_type: string
  text: string
  data: Record<string, unknown>
  status: 'active' | 'superseded' | 'retracted' | 'invalid'
  logical_key?: string | null
  observed_at?: string | null
  created_at?: string | null
  valid_until?: string | null
  source_message_id?: string | null
  provenance?: MemoryProvenance
  supersedes?: string | null
  audit_events?: { action: string; actor_id: string; occurred_at: string; reason?: string }[]
}

export interface MemoryFragment {
  memory_type: EditableMemoryType
  text: string
  logical_key?: string | null
  data?: Record<string, unknown>
  observed_at?: string | null
  valid_until?: string | null
}

export interface ReportStylePreference {
  conclusion_first: boolean
  max_words: number | null
  complex_case_unlimited: boolean
  focus: string[]
}

export interface MemoryWriteResponse {
  status: 'saved'
  records: MemoryRecord[]
  deduplicated: number
  index_available: boolean
  error_code?: string | null
}

const memoryRecordsPath = (threadId: string) => `/memory/threads/${encodeURIComponent(threadId)}/records`
export const listMemoryRecords = (threadId: string, includeInactive = false) =>
  api.get<{ records: MemoryRecord[] }>(memoryRecordsPath(threadId), { params: { include_inactive: includeInactive } })
export const getMemoryHistory = (threadId: string, memoryId: string) =>
  api.get<{ records: MemoryRecord[] }>(`${memoryRecordsPath(threadId)}/${encodeURIComponent(memoryId)}/history`)
export const writeMemoryRecord = (threadId: string, candidate: MemoryFragment) =>
  api.post<MemoryWriteResponse>(memoryRecordsPath(threadId), { candidates: [candidate] })
export const reviseMemoryRecord = (threadId: string, memoryId: string, candidate: MemoryFragment, reason: string) =>
  api.post<MemoryWriteResponse>(`${memoryRecordsPath(threadId)}/${encodeURIComponent(memoryId)}/revise`, { candidate, reason })
export const retractMemoryRecord = (threadId: string, memoryId: string, reason: string) =>
  api.post<{ status: 'retracted'; record: MemoryRecord }>(`${memoryRecordsPath(threadId)}/${encodeURIComponent(memoryId)}/retract`, { reason })
export const getReportStylePreference = () => api.get<Partial<ReportStylePreference>>('/memory/preferences/report-style')
export const saveReportStylePreference = (preference: ReportStylePreference) =>
  api.post<{ status: 'saved'; record: MemoryRecord }>('/memory/preferences/report-style', preference)

// 未登录（401）时统一踢回登录页；登录请求本身除外
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (
      error?.response?.status === 401 &&
      !String(error?.config?.url || '').includes('/auth/')
    ) {
      localStorage.removeItem('martin_doctor')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// 健康检查
export function healthCheck() {
  return api.get('/health')
}

export { AgentWebSocket } from './websocket'
export type { WsStatusMessage } from './websocket'

export default api
