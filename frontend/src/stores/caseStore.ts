import { defineStore } from 'pinia'
import { ref } from 'vue'
import { generateReport } from '../api'

export interface PatientInfo {
  age?: number | string
  gender?: string
  smoking_history?: string
  family_history?: string
  [key: string]: any
}

export interface ImageInfo {
  modality?: string
  image_path?: string
  filename?: string
  image_name?: string
  [key: string]: any
}

export interface Nodule {
  index: number
  diameter: number
  score: number
  center?: { x: number; y: number; z: number }
  dimensions?: { x: number; y: number; z: number }
  [key: string]: any
}

export interface CaseContext {
  patient_info?: PatientInfo
  image_info?: ImageInfo
  nodules?: Nodule[]
  /** True 表示检测工具已经完成；空结节列表此时表示未检出结节。 */
  detection_completed?: boolean
  knowledge_summary?: string
  clinical_notes?: string[]
  risk_factors?: string
  [key: string]: any
}

export interface NoduleInfo {
  index: number
  diameter: number
  score: number
  center: Record<string, number>
  dimensions: Record<string, number>
}

export interface DetectResult {
  image: string
  total_nodules: number
  nodules: NoduleInfo[]
  raw_text: string
}

export type ImageAnalysisStatus = 'uploading' | 'uploaded' | 'analyzing' | 'done' | 'error'

export interface ImageAnalysisFile {
  name: string
  size: number
  status: ImageAnalysisStatus
}

/**
 * 从持久化的病例上下文恢复报告接口所需的检测结果。
 *
 * ``DetectResult`` 是页面运行期状态，而 ``CaseContext`` 会随 session 存入
 * SQLite checkpoint。历史会话恢复后必须以病例上下文为准重建前者，不能因为
 * Pinia 刷新而把已经完成的影像检测视为不存在。
 */
export function detectResultFromCaseContext(ctx: CaseContext = {}): DetectResult | null {
  const nodules = Array.isArray(ctx.nodules) ? ctx.nodules as NoduleInfo[] : []
  // 兼容升级前已经写入 SQLite 的会话：只要保存了结节，便可确定检测已完成。
  // 新数据使用 detection_completed，因而“已检测但 0 个结节”也可以生成报告。
  if (ctx.detection_completed !== true && nodules.length === 0) return null

  const imageInfo = ctx.image_info ?? {}
  const image = imageInfo.image_path || imageInfo.filename || imageInfo.image_name || ''
  return {
    image,
    total_nodules: nodules.length,
    nodules,
    // 原始格式化文本不是报告生成的必要输入，旧 checkpoint 也不会保存它。
    raw_text: '',
  }
}

export const useCaseStore = defineStore('case', () => {
  const detectResult = ref<DetectResult | null>(null)
  const reportContent = ref('')
  const caseContext = ref<CaseContext>({})
  const currentCaseId = ref<string>('')
  // 工作区可能在模型推理期间被路由卸载；上传与分析状态必须属于病例，
  // 而不是属于单个 Vue 组件，才能在返回工作区时恢复。
  const currentFile = ref<ImageAnalysisFile | null>(null)
  const uploadProgress = ref(0)
  const analysisError = ref('')
  const loading = ref(false)
  const error = ref('')

  async function runReport(reportType = 'detailed', language = 'zh') {
    const restoredDetection = detectResult.value ?? detectResultFromCaseContext(caseContext.value)
    if (!restoredDetection) {
      error.value = '请先进行影像检测'
      throw new Error(error.value)
    }
    // 统一使用当前病例恢复出的数据，防止某个路由恢复路径遗漏同步。
    detectResult.value = restoredDetection
    loading.value = true
    error.value = ''
    try {
      const res = await generateReport(
        restoredDetection as unknown as Record<string, unknown>,
        reportType,
        language,
        caseContext.value
      )
      reportContent.value = res.data.report
      return res.data.report
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '报告生成失败'
      error.value = message
      throw err
    } finally {
      loading.value = false
    }
  }

  function updateCaseContext(ctx: Record<string, unknown>) {
    caseContext.value = ctx ?? {}
    detectResult.value = detectResultFromCaseContext(caseContext.value)
  }

  function restore(ctx: Record<string, unknown> = {}) {
    caseContext.value = ctx
    detectResult.value = detectResultFromCaseContext(caseContext.value)
    reportContent.value = ''
    error.value = ''
    const imageInfo = ctx.image_info as ImageInfo | undefined
    const imageName = imageInfo?.filename || imageInfo?.image_name
    currentFile.value = imageName
      ? { name: imageName, size: 0, status: 'done' }
      : null
    uploadProgress.value = 0
    analysisError.value = ''
  }

  function reset() {
    restore({})
  }

  return {
    detectResult,
    reportContent,
    caseContext,
    currentCaseId,
    currentFile,
    uploadProgress,
    analysisError,
    loading,
    error,
    runReport,
    updateCaseContext,
    restore,
    reset,
  }
})
