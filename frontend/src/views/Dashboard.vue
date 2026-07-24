<template>
  <div class="dashboard page-content">
    <section class="worklist-hero">
      <div>
        <span class="eyebrow">MARTIN · RADIOLOGY WORKLIST</span>
        <h1>影像分析工作台</h1>
        <p>从 CT 检测、结节复核到辅助报告，围绕同一份病例持续工作。</p>
      </div>
      <div class="hero-actions">
        <span class="service-state" :class="{ 'is-offline': !healthOk }">
          <i />{{ healthOk ? '服务正常' : '服务离线' }}
        </span>
        <el-button type="primary" size="large" @click="startNewCase">开始影像分析</el-button>
      </div>
    </section>

    <section class="worklist-metrics">
      <div class="metric-card">
        <span>当前工作病例</span>
        <strong>1</strong>
        <small>可从工作区继续分析</small>
      </div>
      <div class="metric-card">
        <span>历史病例记录</span>
        <strong>{{ sessionStore.sessions.length }}</strong>
        <small>支持恢复上下文与对话</small>
      </div>
      <div class="metric-card metric-card--action">
        <span>下一步</span>
        <strong>上传 CT</strong>
        <small>启动结节检测与辅助诊断</small>
      </div>
    </section>

    <section class="session-section">
      <div class="section-heading">
        <div><span class="eyebrow">RECENT CASES</span><h2>最近病例记录</h2></div>
        <el-button text @click="$router.push('/sessions')">查看全部记录</el-button>
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
            <small>最近更新 · {{ formatDate(session.updated_at) }}</small>
          </span>
          <span class="open-label">继续分析 →</span>
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

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.section-heading h2 {
  margin: 0;
}

.worklist-hero {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 28px;
  padding: 16px 0 24px;
}

.eyebrow { color: #688094; font-size: 11px; font-weight: 700; letter-spacing: .1em; }
.worklist-hero h1 { margin: 8px 0 6px; font-size: clamp(28px, 3vw, 38px); letter-spacing: -.035em; }
.worklist-hero p { margin: 0; color: #607080; }
.hero-actions { display: flex; align-items: center; gap: 14px; flex: 0 0 auto; }
.service-state { display: flex; align-items: center; gap: 7px; color: #39765b; font-size: 13px; }
.service-state i { width: 8px; height: 8px; border-radius: 50%; background: #39a96b; }
.service-state.is-offline { color: #a34d45; }.service-state.is-offline i { background: #c65b51; }

.worklist-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}

.metric-card {
  display: flex;
  min-width: 0;
  min-height: 112px;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 10px;
}
.metric-card span, .metric-card small { color: #687888; font-size: 12px; }.metric-card strong { font-size: 26px; }.metric-card--action { background: #e8f3ee; border-color: #c7dfd2; }

.session-section {
  margin-top: 22px;
  padding: 18px;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 10px;
}

.section-heading h2 { margin-top: 4px; font-size: 19px; }

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
  color: #16754e;
  font-size: 13px;
}

@media (max-width: 700px) {
  .worklist-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-actions { width: 100%; justify-content: space-between; }

  .worklist-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
