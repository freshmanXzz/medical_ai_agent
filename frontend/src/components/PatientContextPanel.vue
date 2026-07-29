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
          <div v-if="imageInfo.filename || imageInfo.image_name" class="info-row info-row--column">
            <span class="info-label">影像文件</span>
            <strong class="info-value info-value--break">{{ imageInfo.filename || imageInfo.image_name }}</strong>
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Picture, User, Warning } from '@element-plus/icons-vue'

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
  image_name?: string | null
  filename?: string | null
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

// 影像信息：仅当存在 modality 或可显示文件名时才展示
const imageInfo = computed<ImageInfo | null>(() => {
  const info = props.caseContext?.image_info
  if (!info || typeof info !== 'object') return null
  if (info.modality || info.filename || info.image_name) {
    return info as ImageInfo
  }
  return null
})

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

// 是否存在任何可展示的病例上下文（结节列表由工作区“AI 发现”统一承载）
const hasContext = computed(() => {
  return Boolean(
    patientInfo.value ||
      imageInfo.value ||
      riskFactors.value
  )
})

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
  background: #ffffff;
  border: 1px solid #d7e0e6;
  border-radius: 10px;
}

.context-card :deep(.el-card__header) {
  padding: 10px 12px;
  background: #f7faf9;
  border-bottom: 1px solid #e2e9ed;
}

.context-card :deep(.el-card__body) {
  padding: 10px 12px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #2c7054;
  font-size: 13px;
  font-weight: 600;
}

.card-header .el-icon {
  font-size: 15px;
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
  color: #718494;
}

.info-value {
  color: #314858;
  font-weight: 500;
  text-align: right;
  overflow-wrap: anywhere;
}

.info-value--break {
  word-break: break-all;
  text-align: left;
  font-size: 12px;
}

.risk-text {
  color: #314858;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.case-context-panel :deep(.el-empty__description) {
  color: #718494;
}
</style>
