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
  detectionResult: Record<string, unknown>,
  reportType = 'detailed',
  language = 'zh',
  caseContext: Record<string, unknown> = {}
) =>
  api.post('/report/generate', {
    detection_result: detectionResult,
    report_type: reportType,
    language,
    case_context: caseContext,
  })

// 会话列表
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

// 健康检查
export function healthCheck() {
  return api.get('/health')
}

export { AgentWebSocket } from './websocket'
export type { WsStatusMessage } from './websocket'

export default api
