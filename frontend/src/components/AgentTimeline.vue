<template>
  <div v-if="events.length" class="agent-timeline">
    <el-timeline>
      <el-timeline-item
        v-for="(event, index) in events"
        :key="index"
        :type="timelineType(event.type)"
        :hollow="event.type === 'final'"
        placement="top"
        :timestamp="event.timestamp"
      >
        <div :class="['timeline-event', `is-${event.type}`]">
          <!-- 工具调用：展示调用工具名并附带加载动画 -->
          <template v-if="event.type === 'tool_call'">
            <div class="event-content event-tool">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>调用 {{ event.tool_name || '工具' }}…</span>
            </div>
          </template>

          <!-- 观察结果：截断至 200 字符并展示省略号 -->
          <template v-else-if="event.type === 'observation'">
            <div class="event-content event-observation">
              <el-text class="observation-text" truncated>
                {{ truncate(event.content, 200) }}
              </el-text>
            </div>
          </template>

          <!-- 最终结果：展示分析完成指示 -->
          <template v-else-if="event.type === 'final'">
            <div class="event-content event-final">
              <el-icon><CircleCheckFilled /></el-icon>
              <span>分析完成</span>
            </div>
          </template>

          <!-- 状态文本：如"处理中…""完成" -->
          <template v-else>
            <div class="event-content event-status">{{ event.content }}</div>
          </template>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { CircleCheckFilled, Loading } from '@element-plus/icons-vue'

/** Agent 事件类型 */
type AgentEventType = 'tool_call' | 'observation' | 'final' | 'status'

/** 单条 Agent 事件 */
interface AgentEvent {
  type: AgentEventType
  content: string
  tool_name?: string
  timestamp?: string
}

defineProps<{
  events: AgentEvent[]
}>()

/** 根据事件类型映射时间线节点颜色 */
function timelineType(type: AgentEventType): 'primary' | 'success' | 'info' {
  switch (type) {
    case 'tool_call':
      return 'primary'
    case 'observation':
      return 'success'
    case 'final':
      return 'success'
    case 'status':
      return 'info'
    default:
      return 'info'
  }
}

/** 截断文本至指定最大长度并追加省略号 */
function truncate(text: string, maxLength: number): string {
  if (!text) return ''
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text
}
</script>

<style scoped>
.agent-timeline {
  width: 100%;
  padding: 4px 4px 4px 0;
}

.agent-timeline :deep(.el-timeline-item__timestamp) {
  color: #8a92a6;
  font-size: 11px;
}

.agent-timeline :deep(.el-timeline-item__tail) {
  border-left-color: #0f3460;
}

.agent-timeline :deep(.el-timeline-item__node) {
  background: #0f3460;
}

.agent-timeline :deep(.el-timeline-item__node--primary) {
  background: #53c9b1;
}

.agent-timeline :deep(.el-timeline-item__node--success) {
  background: #24a06b;
}

.agent-timeline :deep(.el-timeline-item__node--info) {
  background: #8a92a6;
}

.timeline-event {
  width: 100%;
}

.event-content {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
}

/* 工具调用：青蓝色 */
.event-tool {
  color: #53c9b1;
  font-weight: 500;
}

.event-tool .el-icon.is-loading,
.event-status .el-icon.is-loading {
  animation: agent-timeline-rotate 1.2s linear infinite;
}

/* 观察结果：绿色，文本为浅色 */
.event-observation {
  align-items: flex-start;
}

.observation-text {
  display: block;
  max-width: 100%;
  color: #e0e6ed;
  font-size: 12px;
}

/* 最终结果：主色高亮 */
.event-final {
  color: #53c9b1;
  font-weight: 600;
}

/* 状态文本：中性灰 */
.event-status {
  color: #8a92a6;
}

@keyframes agent-timeline-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
