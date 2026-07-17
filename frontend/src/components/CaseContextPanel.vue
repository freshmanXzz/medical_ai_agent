<template>
  <div class="case-context-panel">
    <el-empty v-if="!hasContext" description="暂无病例数据" :image-size="80" />

    <template v-else>
      <!-- 患者信息 -->
      <el-card v-if="patientInfo" class="context-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><User /></el-icon>
            <span>患者信息</span>
          </div>
        </template>
        <div class="info-list">
          <div v-if="patientInfo.age != null && patientInfo.age !== ''" class="info-row">
            <span class="info-label">年龄</span>
            <strong class="info-value">{{ patientInfo.age }} 岁</strong>
          </div>
          <div v-if="patientInfo.gender" class="info-row">
            <span class="info-label">性别</span>
            <strong class="info-value">{{ patientInfo.gender }}</strong>
          </div>
          <div v-if="patientInfo.smoking_history" class="info-row">
            <span class="info-label">吸烟史</span>
            <strong class="info-value">{{ patientInfo.smoking_history }}</strong>
          </div>
          <div v-if="patientInfo.family_history" class="info-row">
            <span class="info-label">家族史</span>
            <strong class="info-value">{{ patientInfo.family_history }}</strong>
          </div>
        </div>
      </el-card>

      <!-- 影像信息 -->
      <el-card v-if="imageInfo" class="context-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Picture /></el-icon>
            <span>影像信息</span>
          </div>
        </template>
        <div class="info-list">
          <div v-if="imageInfo.modality" class="info-row">
            <span class="info-label">模态</span>
            <strong class="info-value">{{ imageInfo.modality }}</strong>
          </div>
          <div v-if="imageInfo.image_path" class="info-row info-row--column">
            <span class="info-label">影像路径</span>
            <strong class="info-value info-value--break">{{ imageInfo.image_path }}</strong>
          </div>
        </div>
      </el-card>

      <!-- 检测结果 -->
      <el-card v-if="hasNodules" class="context-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Aim /></el-icon>
            <span>检测结果</span>
            <el-tag size="small" type="success" effect="dark" class="header-tag">
              {{ nodules.length }} 个结节
            </el-tag>
          </div>
        </template>
        <div class="nodule-list">
          <div v-for="nodule in nodules" :key="nodule.index" class="nodule-item">
            <div class="nodule-head">
              <strong>结节 {{ nodule.index }}</strong>
              <el-tag size="small" effect="dark" type="warning">
                {{ formatDiameter(nodule.diameter) }}
              </el-tag>
            </div>
            <div class="nodule-meta">
              <span class="meta-item">置信度：{{ formatScore(nodule.score) }}</span>
              <span v-if="nodule.center" class="meta-item">
                中心：{{ formatPoint(nodule.center) }}
              </span>
            </div>
            <div v-if="nodule.dimensions" class="nodule-dim">
              尺寸：{{ formatPoint(nodule.dimensions) }}
            </div>
          </div>
        </div>
      </el-card>

      <!-- 风险因素 -->
      <el-card v-if="riskFactors" class="context-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Warning /></el-icon>
            <span>风险因素</span>
          </div>
        </template>
        <div class="risk-text">{{ formatRiskFactors(riskFactors) }}</div>
      </el-card>

      <!-- 知识摘要 -->
      <el-card v-if="knowledgeSummary" class="context-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Document /></el-icon>
            <span>知识摘要</span>
          </div>
        </template>
        <div class="summary-text">{{ knowledgeSummary }}</div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Aim, Document, Picture, User, Warning } from '@element-plus/icons-vue'

/** 单个结节信息 */
interface NoduleInfo {
  index: number
  diameter: number
  score: number
  center?: Record<string, number>
  dimensions?: Record<string, number>
}

/** 患者信息 */
interface PatientInfo {
  age?: number | string | null
  gender?: string | null
  smoking_history?: string | null
  family_history?: string | null
}

/** 影像信息 */
interface ImageInfo {
  modality?: string | null
  image_path?: string | null
  image_name?: string | null
}

const props = defineProps<{
  caseContext: Record<string, any>
}>()

// 患者信息：仅当存在非空字段时才展示
const patientInfo = computed<PatientInfo | null>(() => {
  const info = props.caseContext?.patient_info
  if (!info || typeof info !== 'object') return null
  const hasValue = Object.values(info).some(
    (value) => value !== null && value !== '' && value !== undefined
  )
  return hasValue ? (info as PatientInfo) : null
})

// 影像信息：仅当存在 modality 或 image_path 时才展示
const imageInfo = computed<ImageInfo | null>(() => {
  const info = props.caseContext?.image_info
  if (!info || typeof info !== 'object') return null
  if (info.modality || info.image_path || info.image_name) {
    return info as ImageInfo
  }
  return null
})

// 结节列表
const nodules = computed<NoduleInfo[]>(() => {
  const list = props.caseContext?.nodules
  return Array.isArray(list) ? list : []
})

const hasNodules = computed(() => nodules.value.length > 0)

// 风险因素：支持字符串或对象结构
const riskFactors = computed<Record<string, unknown> | string | null>(() => {
  const risk = props.caseContext?.risk_factors
  if (!risk) return null
  if (typeof risk === 'string') return risk.trim() ? risk : null
  if (typeof risk === 'object') {
    const hasValue = Object.values(risk).some(
      (value) => value !== null && value !== '' && value !== undefined
    )
    return hasValue ? (risk as Record<string, unknown>) : null
  }
  return null
})

// 知识摘要：仅支持字符串
const knowledgeSummary = computed<string | null>(() => {
  const summary = props.caseContext?.knowledge_summary
  if (!summary || typeof summary !== 'string') return null
  return summary.trim() ? summary : null
})

// 是否存在任何可展示的上下文
const hasContext = computed(() => {
  return Boolean(
    patientInfo.value ||
      imageInfo.value ||
      hasNodules.value ||
      riskFactors.value ||
      knowledgeSummary.value
  )
})

/** 格式化结节直径 */
function formatDiameter(diameter: number): string {
  if (typeof diameter !== 'number' || Number.isNaN(diameter)) return '--'
  return `${diameter.toFixed(2)} mm`
}

/** 格式化置信度分数为百分比 */
function formatScore(score: number): string {
  if (typeof score !== 'number' || Number.isNaN(score)) return '--'
  return `${(score * 100).toFixed(1)}%`
}

/** 格式化坐标/尺寸点对象为可读字符串 */
function formatPoint(point: Record<string, number>): string {
  const entries = Object.entries(point)
    .filter(([, value]) => typeof value === 'number')
    .map(([key, value]) => `${key}: ${value}`)
  return entries.length ? entries.join('，') : '--'
}

/** 格式化风险因素：对象结构拼接为 key: value 形式 */
function formatRiskFactors(risk: Record<string, unknown> | string): string {
  if (typeof risk === 'string') return risk
  const entries = Object.entries(risk)
    .filter(([, value]) => value !== null && value !== '' && value !== undefined)
    .map(([key, value]) => `${key}: ${value}`)
  return entries.length ? entries.join('；') : '暂无'
}
</script>

<style scoped>
.case-context-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.context-card {
  background: #16213e;
  border: 1px solid #0f3460;
  border-radius: 8px;
}

.context-card :deep(.el-card__header) {
  padding: 10px 12px;
  background: #1a1a2e;
  border-bottom: 1px solid #0f3460;
}

.context-card :deep(.el-card__body) {
  padding: 10px 12px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #53c9b1;
  font-size: 13px;
  font-weight: 600;
}

.card-header .el-icon {
  font-size: 15px;
}

.header-tag {
  margin-left: auto;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.info-row--column {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.info-label {
  color: #8a92a6;
}

.info-value {
  color: #e0e6ed;
  font-weight: 500;
  text-align: right;
  overflow-wrap: anywhere;
}

.info-value--break {
  word-break: break-all;
  text-align: left;
  font-size: 12px;
}

.nodule-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nodule-item {
  padding: 8px;
  background: #1a1a2e;
  border: 1px solid #0f3460;
  border-radius: 6px;
}

.nodule-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #e0e6ed;
  font-size: 13px;
}

.nodule-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 4px;
  color: #8a92a6;
  font-size: 11px;
}

.nodule-dim {
  margin-top: 4px;
  color: #8a92a6;
  font-size: 11px;
}

.risk-text,
.summary-text {
  color: #e0e6ed;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.case-context-panel :deep(.el-empty__description) {
  color: #8a92a6;
}
</style>
