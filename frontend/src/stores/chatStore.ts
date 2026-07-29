import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatWithAgent, getSessionDetail, AgentWebSocket } from '../api'
import { useCaseStore } from './caseStore'

export interface ToolCallInfo {
  tool_name: string
  tool_args: Record<string, unknown>
  output: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: ToolCallInfo[]
}

export interface TimelineEvent {
  type: 'tool_call' | 'observation' | 'final' | 'status'
  content: string
  tool_name?: string
  timestamp?: string
}

export interface AttachmentInfo {
  filename: string
  medical_image: boolean
}

const WELCOME_MESSAGE = '您好，我是 Martin 影像分析助手。请上传 CT 影像文件开始病例分析。'

function initialMessages(): ChatMessage[] {
  return [{ role: 'assistant', content: WELCOME_MESSAGE }]
}

function createSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `session_${Date.now()}`
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>(initialMessages())
  const loading = ref(false)
  const sessionId = ref(createSessionId())
  const error = ref<string | null>(null)
  const timeline = ref<TimelineEvent[]>([])

  async function sendMessage(
    userMessage: string,
    caseContext: Record<string, any> = {},
    attachment?: AttachmentInfo
  ) {
    loading.value = true
    error.value = null
    timeline.value = []

    // 添加用户消息（附带文件名时拼接展示文本）
    const displayMessage = attachment
      ? `${userMessage || `已上传文件: ${attachment.filename}`}`
      : userMessage
    messages.value.push({ role: 'user', content: displayMessage })

    try {
      // 优先尝试 WebSocket 流式通信
      const ws = new AgentWebSocket(sessionId.value)

      await new Promise<void>((resolve, reject) => {
        // 影像分析等工具可能耗时数分钟，超时设为 10 分钟
        const timeout = setTimeout(() => {
          ws.disconnect()
          reject(new Error('WebSocket timeout'))
        }, 600000)

        ws.onStatus((data) => {
          // 只展示用户可理解的状态消息，跳过内部技术状态
          const skipPatterns = ['会话已连接']
          if (skipPatterns.some((p) => data.content.includes(p))) return
          timeline.value.push({
            type: 'status',
            content: data.content,
            timestamp: data.timestamp,
          })
        })

        ws.onCaseContext((data) => {
          try {
            const parsed = JSON.parse(data.content)
            if (parsed.case_context) {
              const caseStore = useCaseStore()
              caseStore.updateCaseContext(parsed.case_context)
            }
          } catch {
            // 解析失败，忽略
          }
        })

        ws.onToolCall((data) => {
          timeline.value.push({
            type: 'tool_call',
            content: `调用 ${data.tool_name}…`,
            tool_name: data.tool_name,
            timestamp: data.timestamp,
          })
        })

        ws.onObservation((data) => {
          timeline.value.push({
            type: 'observation',
            content: data.content,
            timestamp: data.timestamp,
          })
        })

        ws.onFinal((data) => {
          messages.value.push({ role: 'assistant', content: data.content })
          clearTimeout(timeout)
          resolve()
        })

        ws.onError((data) => {
          messages.value.push({ role: 'assistant', content: data.content })
          clearTimeout(timeout)
          resolve()
        })

        ws.connect()
          .then(() => {
            ws.send(
              userMessage || (attachment ? `已上传文件: ${attachment.filename}` : ''),
              attachment
            )
          })
          .catch((err) => {
            clearTimeout(timeout)
            reject(err)
          })
      })

      ws.disconnect()
    } catch (wsError) {
      // WebSocket 失败时回退到 REST API
      console.warn('WebSocket failed, falling back to REST:', wsError)
      try {
        const res = await chatWithAgent(sessionId.value, userMessage, caseContext)
        messages.value.push({
          role: 'assistant',
          content: res.data.output,
          tool_calls: res.data.tool_calls,
        })

        // 同步病例上下文
        if (res.data.case_context) {
          const caseStore = useCaseStore()
          caseStore.updateCaseContext(res.data.case_context)
        }
        return res.data
      } catch (restError: any) {
        error.value = restError.response?.data?.detail || restError.message || '发送消息失败'
        messages.value.push({ role: 'assistant', content: `错误: ${error.value}` })
      }
    } finally {
      loading.value = false
    }
  }

  async function openSession(id: string) {
    const res = await getSessionDetail(id)
    sessionId.value = id
    messages.value = res.data.messages.map((message: { role: string; content: string }) => ({
      role: message.role.toLowerCase() === 'user' ? 'user' : 'assistant',
      content: message.content,
    }))
    if (!messages.value.length) messages.value = initialMessages()
    error.value = ''
    return res.data
  }

  function newSession() {
    sessionId.value = createSessionId()
    messages.value = initialMessages()
    error.value = ''
    return sessionId.value
  }

  return {
    messages,
    loading,
    sessionId,
    error,
    timeline,
    sendMessage,
    openSession,
    newSession,
  }
})
