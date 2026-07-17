<template>
  <div class="sessions-page">
    <div class="page-heading">
      <div>
        <h1>会话管理</h1>
        <p>查看历史记录，或继续之前的病例对话。</p>
      </div>
      <el-button type="primary" @click="handleNewSession">新建会话</el-button>
    </div>

    <el-alert
      v-if="sessionStore.error"
      :title="sessionStore.error"
      type="error"
      :closable="false"
      show-icon
    />

    <div v-loading="sessionStore.loading" class="session-list">
      <el-empty v-if="!sessionStore.loading && !sessionStore.sessions.length" description="暂无历史会话" />
      <article v-for="session in sessionStore.sessions" :key="session.thread_id" class="session-item">
        <div class="session-main">
          <h2>{{ session.title }}</h2>
          <span class="session-id">{{ session.thread_id }}</span>
          <small>最近更新：{{ formatDate(session.updated_at) }}</small>
        </div>
        <div class="session-actions">
          <el-button @click="handleView(session.thread_id)">查看记录</el-button>
          <el-button type="primary" @click="handleSwitch(session.thread_id)">继续对话</el-button>
        </div>
      </article>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="min(720px, 92vw)">
      <div class="history-list">
        <div
          v-for="(message, index) in currentMessages"
          :key="index"
          :class="['history-message', message.role === 'User' ? 'is-user' : 'is-agent']"
        >
          <strong>{{ message.role === 'User' ? '用户' : 'Martin' }}</strong>
          <p>{{ message.content }}</p>
        </div>
        <el-empty v-if="!currentMessages.length" description="暂无消息" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '../stores/sessionStore'
import { useChatStore } from '../stores/chatStore'
import { useCaseStore } from '../stores/caseStore'
import { getSessionDetail } from '../api'

const router = useRouter()
const sessionStore = useSessionStore()
const chatStore = useChatStore()
const caseStore = useCaseStore()
const dialogVisible = ref(false)
const dialogTitle = ref('会话记录')
const currentMessages = ref<{ role: string; content: string }[]>([])

onMounted(() => sessionStore.fetchSessions())

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

async function handleView(threadId: string) {
  try {
    const res = await getSessionDetail(threadId)
    dialogTitle.value = res.data.title
    currentMessages.value = res.data.messages
    dialogVisible.value = true
  } catch {
    ElMessage.error('加载会话详情失败')
  }
}

async function handleSwitch(threadId: string) {
  try {
    const detail = await chatStore.openSession(threadId)
    caseStore.restore(detail.case_context)
    await router.push('/workspace')
  } catch {
    ElMessage.error('切换会话失败')
  }
}

function handleNewSession() {
  chatStore.newSession()
  caseStore.reset()
  router.push('/workspace')
}
</script>

<style scoped>
.sessions-page {
  width: min(1040px, 100%);
  margin: 0 auto;
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.page-heading h1 {
  margin: 0;
  font-size: 26px;
}

.page-heading p {
  margin: 6px 0 0;
  color: #6b7785;
}

.session-list {
  min-height: 180px;
  margin-top: 14px;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 6px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 18px;
  border-bottom: 1px solid #edf0f2;
}

.session-item:last-child {
  border-bottom: 0;
}

.session-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.session-main h2 {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 16px;
}

.session-id,
.session-main small {
  color: #75818c;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.session-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.history-list {
  display: flex;
  max-height: 60vh;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.history-message {
  width: min(88%, 600px);
  padding: 10px 12px;
  border-radius: 6px;
}

.history-message p {
  margin: 5px 0 0;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.history-message.is-user {
  align-self: flex-end;
  background: #e9f5ef;
}

.history-message.is-agent {
  align-self: flex-start;
  background: #f0f2f4;
}

@media (max-width: 700px) {
  .page-heading,
  .session-item {
    align-items: stretch;
    flex-direction: column;
  }

  .session-actions .el-button {
    flex: 1;
    margin-left: 0;
  }
}
</style>
