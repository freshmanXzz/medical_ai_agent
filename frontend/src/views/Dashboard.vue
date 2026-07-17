<template>
  <div class="dashboard page-content">
    <div class="page-heading">
      <div>
        <h1>Martin</h1>
        <p>AI Medical Imaging Copilot</p>
        <p class="subtitle">医学影像分析 · 病例辅助理解 · 影像报告生成</p>
      </div>
      <el-button type="primary" @click="startNewCase">新建病例分析</el-button>
    </div>

    <section class="status-grid">
      <div class="status-panel">
        <span>系统状态</span>
        <el-tag :type="healthOk ? 'success' : 'danger'">
          {{ healthOk ? '运行中' : '离线' }}
        </el-tag>
      </div>
      <div class="status-panel">
        <span>当前病例</span>
        <strong class="session-id">{{ chatStore.sessionId }}</strong>
      </div>
      <div class="status-panel">
        <span>历史病例</span>
        <strong>{{ sessionStore.sessions.length }} 个</strong>
      </div>
    </section>

    <section class="session-section">
      <div class="section-heading">
        <h2>最近病例分析记录</h2>
        <el-button text @click="$router.push('/sessions')">查看全部</el-button>
      </div>

      <el-skeleton v-if="sessionStore.loading" :rows="4" animated />
      <el-empty v-else-if="!sessionStore.sessions.length" description="暂无历史病例" />
      <div v-else class="recent-list">
        <button
          v-for="session in sessionStore.sessions.slice(0, 5)"
          :key="session.thread_id"
          class="session-row"
          type="button"
          @click="openSession(session.thread_id)"
        >
          <span class="session-copy">
            <strong>{{ session.title }}</strong>
            <small>{{ formatDate(session.updated_at) }}</small>
          </span>
          <span class="open-label">打开</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '../stores/sessionStore'
import { useChatStore } from '../stores/chatStore'
import { useCaseStore } from '../stores/caseStore'
import { healthCheck } from '../api'

const router = useRouter()
const sessionStore = useSessionStore()
const chatStore = useChatStore()
const caseStore = useCaseStore()
const healthOk = ref(false)

onMounted(async () => {
  await sessionStore.fetchSessions()
  try {
    await healthCheck()
    healthOk.value = true
  } catch {
    healthOk.value = false
  }
})

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function startNewCase() {
  chatStore.newSession()
  caseStore.reset()
  router.push('/workspace')
}

async function openSession(threadId: string) {
  try {
    const detail = await chatStore.openSession(threadId)
    caseStore.restore(detail.case_context)
    await router.push('/workspace')
  } catch {
    ElMessage.error('打开历史会话失败')
  }
}
</script>

<style scoped>
.page-content {
  width: min(1120px, 100%);
  margin: 0 auto;
}

.page-heading,
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-heading h1,
.section-heading h2 {
  margin: 0;
}

.page-heading h1 {
  font-size: 26px;
}

.page-heading p {
  margin: 6px 0 0;
  color: #6b7785;
}

.page-heading .subtitle {
  margin-top: 2px;
  font-size: 13px;
  color: #97a0ab;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}

.status-panel {
  display: flex;
  min-width: 0;
  min-height: 86px;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 6px;
}

.status-panel > span:first-child {
  color: #6b7785;
  font-size: 13px;
}

.session-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-section {
  margin-top: 22px;
  padding: 18px;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 6px;
}

.section-heading h2 {
  font-size: 18px;
}

.recent-list {
  margin-top: 12px;
  border-top: 1px solid #edf0f2;
}

.session-row {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 4px;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  border-bottom: 1px solid #edf0f2;
  cursor: pointer;
}

.session-row:hover {
  background: #f7faf8;
}

.session-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.session-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-copy small {
  color: #7b8792;
}

.open-label {
  flex: 0 0 auto;
  color: #16875b;
  font-size: 13px;
}

@media (max-width: 700px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
