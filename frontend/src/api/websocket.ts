export interface WsStatusMessage {
  type: 'status' | 'tool_call' | 'observation' | 'final' | 'error' | 'case_context'
  content: string
  tool_name?: string
  timestamp: string
}

type MessageHandler = (msg: WsStatusMessage) => void

export class AgentWebSocket {
  private ws: WebSocket | null = null
  private sessionId: string
  private handlers: MessageHandler[] = []
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectDelay = 3000

  constructor(sessionId: string) {
    this.sessionId = sessionId
  }

  connect(): Promise<void> {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/api/ws/agent/${this.sessionId}`

    this.ws = new WebSocket(url)

    return new Promise<void>((resolve, reject) => {
      if (!this.ws) {
        reject(new Error('WebSocket 创建失败'))
        return
      }

      this.ws.onopen = () => {
        console.log('WebSocket 已连接')
        resolve()
      }

      this.ws.onmessage = (event) => {
        try {
          const msg: WsStatusMessage = JSON.parse(event.data)
          this.handlers.forEach((h) => h(msg))
        } catch {
          console.warn('WebSocket 消息解析失败:', event.data)
        }
      }

      this.ws.onclose = () => {
        console.log('WebSocket 已断开，尝试重连...')
        this.scheduleReconnect()
      }

      this.ws.onerror = (err) => {
        console.error('WebSocket 错误:', err)
        reject(err)
      }
    })
  }

  send(message: string, attachment?: { object_key: string; filename: string; medical_image: boolean }) {
    const payload: any = { message }
    if (attachment) {
      payload.attachment = attachment
    }
    this.ws?.send(JSON.stringify(payload))
  }

  onMessage(handler: MessageHandler) {
    this.handlers.push(handler)
  }

  onToolCall(handler: (data: WsStatusMessage) => void): void {
    this.handlers.push((msg) => {
      if (msg.type === 'tool_call') handler(msg)
    })
  }

  onObservation(handler: (data: WsStatusMessage) => void): void {
    this.handlers.push((msg) => {
      if (msg.type === 'observation') handler(msg)
    })
  }

  onFinal(handler: (data: WsStatusMessage) => void): void {
    this.handlers.push((msg) => {
      if (msg.type === 'final') handler(msg)
    })
  }

  onStatus(handler: (data: WsStatusMessage) => void): void {
    this.handlers.push((msg) => {
      if (msg.type === 'status') handler(msg)
    })
  }

  onCaseContext(handler: (data: WsStatusMessage) => void): void {
    this.handlers.push((msg) => {
      if (msg.type === 'case_context') handler(msg)
    })
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, this.reconnectDelay)
  }
}
