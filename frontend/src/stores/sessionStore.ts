import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listSessions } from '../api'

export interface SessionSummary {
  thread_id: string
  title: string
  created_at: string
  updated_at: string
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<SessionSummary[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchSessions() {
    loading.value = true
    error.value = ''
    try {
      const res = await listSessions()
      sessions.value = res.data.sessions
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : '获取会话列表失败'
      console.error('获取会话列表失败:', err)
    } finally {
      loading.value = false
    }
  }

  return { sessions, loading, error, fetchSessions }
})
