<template>
  <div class="image-uploader">
    <!-- 上传区域：支持拖拽与点击，不自动上传，交由父组件处理 -->
    <el-upload
      :auto-upload="false"
      :show-file-list="false"
      accept=".nii,.nii.gz"
      :on-change="handleFileChange"
      drag
      class="uploader-zone"
    >
      <el-icon class="uploader-icon"><UploadFilled /></el-icon>
      <div class="uploader-text">拖拽 CT 影像文件到此处，或点击上传</div>
      <template #tip>
        <div class="uploader-tip">支持 .nii / .nii.gz 格式</div>
      </template>
    </el-upload>

    <!-- 当前文件信息 -->
    <div v-if="currentFile" class="file-info">
      <div class="file-head">
        <el-icon class="file-icon"><Document /></el-icon>
        <div class="file-meta">
          <strong class="file-name">{{ currentFile.name }}</strong>
          <small class="file-size">{{ formatFileSize(currentFile.size) }}</small>
        </div>
        <el-tag :type="statusTagType" size="small" effect="dark">
          {{ statusText }}
        </el-tag>
      </div>

      <!-- 上传进度条 -->
      <el-progress
        v-if="currentFile.status === 'uploading'"
        :percentage="uploadProgress"
        :stroke-width="6"
        :show-text="false"
        color="#53c9b1"
      />

      <!-- 分析中状态 -->
      <div v-if="currentFile.status === 'analyzing'" class="status-line">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>分析中...</span>
      </div>

      <!-- 已上传状态 -->
      <div v-if="currentFile.status === 'uploaded'" class="status-line is-success">
        <el-icon><CircleCheck /></el-icon>
        <span>已上传</span>
      </div>

      <!-- 分析完成状态 -->
      <div v-if="currentFile.status === 'done'" class="status-line is-success">
        <el-icon><CircleCheckFilled /></el-icon>
        <span>分析完成</span>
      </div>

      <div v-if="currentFile.status === 'error'" class="status-line is-error">
        <el-icon><CircleCloseFilled /></el-icon>
        <span>分析失败，请重新上传或查看错误提示</span>
      </div>
    </div>

    <!-- 检测摘要：逐项复核统一在工作区的“AI 发现”列表中完成，避免重复罗列结节。 -->
    <div v-if="detectionResult && detectionResult.total_nodules > 0" class="detection-result">
      <div class="result-summary">
        <el-icon><Aim /></el-icon>
        <span>检测到 <strong>{{ detectionResult.total_nodules }}</strong> 个结节</span>
      </div>
      <p class="result-hint">在下方“AI 发现”中选择结节进行逐项复核。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Aim,
  CircleCheck,
  CircleCheckFilled,
  CircleCloseFilled,
  Document,
  Loading,
  UploadFilled,
} from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'

/** 文件处理状态 */
type FileStatus = 'idle' | 'uploading' | 'uploaded' | 'analyzing' | 'done' | 'error'

/** 当前文件信息 */
interface CurrentFile {
  name: string
  size: number
  status: FileStatus
}

/** 检测结果集合 */
interface DetectionResult {
  total_nodules: number
}

const props = defineProps<{
  currentFile: CurrentFile | null
  uploadProgress: number
  detectionResult: DetectionResult | null
}>()

const emit = defineEmits<{
  (e: 'upload', file: File): void
}>()

// 状态文本：根据文件状态展示对应文案
const statusText = computed(() => {
  if (!props.currentFile) return ''
  switch (props.currentFile.status) {
    case 'uploading':
      return `上传中 ${props.uploadProgress}%`
    case 'uploaded':
      return '已上传'
    case 'analyzing':
      return '分析中'
      case 'done':
        return '完成'
      case 'error':
        return '失败'
    default:
      return '待处理'
  }
})

// 状态标签颜色：上传中为主色，完成类为成功，分析中为警告
const statusTagType = computed<'info' | 'primary' | 'success' | 'warning' | 'danger'>(() => {
  if (!props.currentFile) return 'info'
  switch (props.currentFile.status) {
    case 'uploading':
      return 'primary'
      case 'uploaded':
      case 'done':
        return 'success'
      case 'error':
        return 'danger'
    case 'analyzing':
      return 'warning'
    default:
      return 'info'
  }
})

/** 文件选择变化时，将原始文件交给父组件处理 */
function handleFileChange(file: UploadFile) {
  if (file.raw) {
    emit('upload', file.raw)
  }
}

/** 格式化文件大小为 KB/MB 可读形式 */
function formatFileSize(size: number): string {
  if (!size || size <= 0) return '--'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(2)} MB`
}

</script>

<style scoped>
.image-uploader {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.uploader-zone {
  width: 100%;
}

.image-uploader :deep(.el-upload) {
  width: 100%;
}

.image-uploader :deep(.el-upload__input) {
  display: none;
}

.image-uploader :deep(.el-upload-dragger) {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 18px 12px;
  background: #f7faf9;
  border: 1px dashed #a9c4b5;
  border-radius: 8px;
  transition: border-color 0.2s ease;
}

.image-uploader :deep(.el-upload-dragger:hover) {
  border-color: #25805a;
  background: #eff7f2;
}

.uploader-icon {
  font-size: 32px;
  color: #25805a;
}

.uploader-text {
  margin-top: 8px;
  color: #314858;
  font-size: 12px;
  text-align: center;
}

.uploader-tip {
  margin-top: 6px;
  color: #718494;
  font-size: 11px;
  text-align: center;
}

.file-info {
  padding: 10px;
  background: #f7faf9;
  border: 1px solid #d8e4de;
  border-radius: 8px;
}

.file-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon {
  color: #25805a;
  font-size: 18px;
  flex-shrink: 0;
}

.file-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  color: #314858;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  color: #718494;
  font-size: 11px;
}

.image-uploader :deep(.el-progress) {
  margin-top: 8px;
}

.status-line {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  color: #718494;
  font-size: 12px;
}

.status-line.is-success {
  color: #25805a;
}

.status-line.is-error {
  color: #c45656;
}

.status-line .el-icon.is-loading {
  animation: image-uploader-rotate 1.2s linear infinite;
}

.detection-result {
  padding: 10px;
  background: #f7faf9;
  border: 1px solid #d8e4de;
  border-radius: 8px;
}

.result-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #25805a;
  font-size: 13px;
}

.result-summary strong {
  color: #314858;
  font-size: 15px;
}

.result-hint {
  margin: 6px 0 0;
  color: #718494;
  font-size: 11px;
  line-height: 1.5;
}

@keyframes image-uploader-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
