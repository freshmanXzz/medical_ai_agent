<template>
  <div class="workspace-page">
    <div class="workspace-heading">
      <div>
        <h1>病例工作区</h1>
        <span>会话 {{ chatStore.sessionId }}</span>
      </div>
      <el-button @click="$router.push('/sessions')">历史会话</el-button>
    </div>

    <div class="workspace-grid">
      <!-- 左栏：CT 影像上传与检测 -->
      <el-card class="detection-panel" shadow="never">
        <template #header>
          <strong>CT 影像检测</strong>
        </template>
        <ImageUploader
          :current-file="currentFile"
          :upload-progress="uploadProgress"
          :detection-result="detectionSummary"
          @upload="handleFileUpload"
        />
      </el-card>

      <!-- 中栏：对话区与 Agent 时间线 -->
      <el-card class="chat-panel" shadow="never">
        <template #header>
          <div class="chat-header">
            <div>
              <strong>Martin 智能体</strong>
              <span :class="['connection-state', chatStore.error ? 'is-error' : '']">
                {{ chatStore.error ? '上次请求失败' : '可以开始对话' }}
              </span>
            </div>
            <el-tag size="small" type="success">Agent</el-tag>
          </div>
        </template>

        <div ref="chatContainer" class="chat-messages" aria-live="polite">
          <div
            v-for="(message, index) in chatStore.messages"
            :key="index"
            :class="['message-row', message.role === 'user' ? 'is-user' : 'is-agent']"
          >
            <div class="message-label">{{ message.role === 'user' ? '用户' : 'Martin' }}</div>
            <div class="message-bubble">{{ message.content }}</div>
            <div v-if="message.tool_calls?.length" class="tool-list">
              <el-tag
                v-for="tool in message.tool_calls"
                :key="tool.tool_name"
                size="small"
                type="info"
              >
                {{ tool.tool_name }}
              </el-tag>
            </div>
          </div>

          <div v-if="chatStore.loading" class="thinking-state">
            <span class="thinking-dot" />
            Martin 正在分析，请稍候...
          </div>
        </div>

        <!-- Agent 时间线：展示工具调用与观察结果 -->
        <AgentTimeline :events="chatStore.timeline" />

        <div class="composer">
          <!-- 已选文件指示器 -->
          <div v-if="selectedFile" class="file-tag">
            <span>{{ selectedFile.name }}</span>
            <el-progress
              v-if="uploadProgress > 0 && uploadProgress < 100"
              :percentage="uploadProgress"
              :stroke-width="3"
            />
            <el-button
              v-if="uploadProgress === 0 || uploadProgress >= 100"
              link
              size="small"
              @click="clearSelectedFile"
            >
              ×
            </el-button>
          </div>
          <div class="input-row">
            <!-- 附件按钮 -->
            <el-upload
              :show-file-list="false"
              :auto-upload="false"
              accept=".nii,.nii.gz,.dcm"
              :on-change="handleFileSelect"
            >
              <el-button :icon="Paperclip" circle />
            </el-upload>
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="输入消息..."
              :disabled="chatStore.loading"
              @keydown.enter.exact.prevent="handleSend"
            />
            <el-button
              type="primary"
              :loading="chatStore.loading"
              :disabled="!inputMessage.trim()"
              @click="handleSend"
            >
              发送
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- 右栏：病例上下文 -->
      <div class="context-column">
        <CaseContextPanel :case-context="caseStore.caseContext" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Paperclip } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import CaseContextPanel from '../components/CaseContextPanel.vue'
import AgentTimeline from '../components/AgentTimeline.vue'
import ImageUploader from '../components/ImageUploader.vue'
import { uploadImage } from '../api'
import type { AttachmentInfo } from '../stores/chatStore'
import { useCaseStore } from '../stores/caseStore'
import { useChatStore } from '../stores/chatStore'

const caseStore = useCaseStore()
const chatStore = useChatStore()

const inputMessage = ref('')
const selectedFile = ref<File | null>(null)
const uploadProgress = ref(0)
const chatContainer = ref<HTMLElement | null>(null)
const currentFile = ref<{
  name: string
  size: number
  status: 'idle' | 'uploading' | 'uploaded' | 'analyzing' | 'done'
} | null>(null)
const detectionSummary = ref<{
  total_nodules: number
  nodules: Array<{ index: number; diameter: number; score: number }>
} | null>(null)

// 消息变化时自动滚动到底部
watch(
  () => [chatStore.messages.length, chatStore.loading],
  async () => {
    await nextTick()
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
)

// 病例上下文变化时同步检测摘要（含会话恢复场景）
watch(
  () => caseStore.caseContext,
  (ctx) => {
    if (ctx?.nodules) {
      detectionSummary.value = {
        total_nodules: ctx.nodules.total_nodules || 0,
        nodules: ctx.nodules.nodules || [],
      }
    }
  },
  { deep: true, immediate: true }
)

/** 文件选择处理：自动触发上传 */
async function handleFileSelect(file: UploadFile) {
  if (!file.raw) return
  selectedFile.value = file.raw
  uploadProgress.value = 0
  currentFile.value = {
    name: file.raw.name,
    size: file.raw.size,
    status: 'uploading',
  }
  await handleFileUpload(file.raw)
}

/** 文件上传到 OSS 并自动发送分析消息 */
async function handleFileUpload(file: File) {
  try {
    currentFile.value = { name: file.name, size: file.size, status: 'uploading' }

    // 上传到 MinIO
    const res = await uploadImage(file, (progress) => {
      uploadProgress.value = progress
    })

    const objectKey = res.data.object_name
    currentFile.value = { name: file.name, size: file.size, status: 'uploaded' }

    // 判断是否为医学影像文件
    const isMedical = /\.(nii|nii\.gz|dcm)$/i.test(file.name)

    // 自动发送带附件的消息
    const attachment: AttachmentInfo = {
      object_key: objectKey,
      filename: file.name,
      medical_image: isMedical,
    }

    currentFile.value = { name: file.name, size: file.size, status: 'analyzing' }
    await chatStore.sendMessage('', caseStore.caseContext as Record<string, any>, attachment)
    currentFile.value = { name: file.name, size: file.size, status: 'done' }

    // 从病例上下文更新检测摘要
    if (caseStore.caseContext?.nodules) {
      detectionSummary.value = {
        total_nodules: caseStore.caseContext.nodules.total_nodules || 0,
        nodules: caseStore.caseContext.nodules.nodules || [],
      }
    }

    selectedFile.value = null
    uploadProgress.value = 0
  } catch (err: unknown) {
    currentFile.value = null
    selectedFile.value = null
    uploadProgress.value = 0
    const message = err instanceof Error ? err.message : '未知错误'
    ElMessage.error(`上传失败: ${message}`)
  }
}

/** 清除已选文件 */
function clearSelectedFile() {
  selectedFile.value = null
  uploadProgress.value = 0
}

/** 发送聊天消息 */
async function handleSend() {
  if (!inputMessage.value.trim() || chatStore.loading) return
  const msg = inputMessage.value
  inputMessage.value = ''
  await chatStore.sendMessage(msg, caseStore.caseContext as Record<string, any>)
}
</script>

<style scoped>
.workspace-page {
  width: 100%;
  min-height: calc(100vh - 44px);
}

.workspace-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.workspace-heading h1 {
  margin: 0;
  font-size: 22px;
}

.workspace-heading span {
  display: block;
  max-width: 70vw;
  margin-top: 4px;
  overflow: hidden;
  color: #75818c;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(250px, 0.78fr) minmax(390px, 1.45fr) minmax(250px, 0.82fr);
  gap: 12px;
  min-height: calc(100vh - 112px);
}

.workspace-grid > *,
.context-column {
  min-width: 0;
}

.chat-panel {
  height: calc(100vh - 112px);
  min-height: 560px;
}

.chat-panel :deep(.el-card__body) {
  display: flex;
  height: calc(100% - 58px);
  min-height: 0;
  flex-direction: column;
  padding: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.chat-header > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.connection-state {
  color: #16875b;
  font-size: 11px;
}

.connection-state.is-error {
  color: #c0392b;
}

.chat-messages {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  overflow-y: auto;
  background: #f8faf9;
}

.message-row {
  display: flex;
  width: min(88%, 680px);
  flex-direction: column;
  gap: 4px;
}

.message-row.is-user {
  align-self: flex-end;
  align-items: flex-end;
}

.message-row.is-agent {
  align-self: flex-start;
}

.message-label {
  color: #75818c;
  font-size: 11px;
}

.message-bubble {
  padding: 10px 12px;
  line-height: 1.65;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 6px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.is-user .message-bubble {
  background: #e5f5ec;
  border-color: #b9dfca;
}

.tool-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.thinking-state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #65727e;
  font-size: 13px;
}

.thinking-dot {
  width: 8px;
  height: 8px;
  background: #24a06b;
  border-radius: 50%;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #ffffff;
  border-top: 1px solid #dfe4e8;
}

.file-tag {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: rgba(83, 201, 177, 0.1);
  border-radius: 4px;
  margin-bottom: 8px;
  font-size: 13px;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.input-row .el-input {
  flex: 1;
}

.context-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 1180px) {
  .workspace-grid {
    grid-template-columns: minmax(240px, 0.8fr) minmax(420px, 1.4fr);
  }

  .context-column {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .workspace-page {
    min-height: 0;
  }

  .workspace-grid {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .chat-panel {
    order: -1;
    height: 68vh;
    min-height: 500px;
  }

  .context-column {
    display: flex;
  }

  .input-row {
    flex-wrap: wrap;
  }
}
</style>
