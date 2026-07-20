<template>
  <div v-if="visibleEvents.length" class="agent-timeline">
    <div class="timeline-header" @click="expanded = !expanded">
      <span class="header-title">Agent 工作过程</span>
      <span class="header-count">{{ visibleEvents.length }} 步</span>
      <el-icon class="header-toggle" :class="{ 'is-expanded': expanded }">
        <ArrowDown />
      </el-icon>
    </div>
    <div v-show="expanded" class="timeline-content">
      <div class="step-list">
        <div
          v-for="(event, index) in visibleEvents"
          :key="index"
          :class="['step-item', `is-${event.type}`]"
        >
          <div class="step-indicator">
            <el-icon v-if="event.type === 'tool_call'" class="is-loading"><Loading /></el-icon>
            <el-icon v-else-if="event.type === 'final'"><CircleCheckFilled /></el-icon>
            <span v-else class="step-dot" />
          </div>
          <div class="step-info">
            <span class="step-name">{{ event.displayName }}</span>
            <span v-if="event.type === 'tool_call'" class="step-detail">
              {{ event.tool_name }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown, CircleCheckFilled, Loading } from '@element-plus/icons-vue'

type AgentEventType = 'tool_call' | 'observation' | 'final' | 'status'

interface AgentEvent {
  type: AgentEventType
  content: string
  tool_name?: string
  timestamp?: string
}

const props = defineProps<{
  events: AgentEvent[]
}>()

const expanded = ref(false)

const visibleEvents = computed(() => {
  const result: Array<AgentEvent & { displayName: string }> = []
  for (const event of props.events) {
    if (event.type === 'tool_call') {
      result.push({
        ...event,
        displayName: `调用 ${event.tool_name || '工具'}`,
      })
    } else if (event.type === 'final') {
      result.push({
        ...event,
        displayName: '生成最终回答',
      })
    }
  }
  return result
})
</script>

<style scoped>
.agent-timeline {
  width: 100%;
  border-top: 1px solid #dfe4e8;
  background: #f8faf9;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  color: #65727e;
  transition: background 0.15s;
}

.timeline-header:hover {
  background: #eef2f0;
}

.header-title {
  font-weight: 500;
}

.header-count {
  padding: 1px 6px;
  background: #e0e6ed;
  border-radius: 10px;
  font-size: 11px;
}

.header-toggle {
  margin-left: auto;
  transition: transform 0.2s;
  font-size: 14px;
}

.header-toggle.is-expanded {
  transform: rotate(180deg);
}

.timeline-content {
  padding: 0 12px 10px;
}

.step-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #ffffff;
  border: 1px solid #dfe4e8;
  border-radius: 4px;
  font-size: 12px;
}

.step-item.is-tool_call {
  border-color: #b9dfca;
  background: #e5f5ec;
  color: #16875b;
}

.step-item.is-final {
  border-color: #53c9b1;
  background: #d6f5eb;
  color: #0e6b4a;
  font-weight: 500;
}

.step-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-dot {
  width: 6px;
  height: 6px;
  background: #8a92a6;
  border-radius: 50%;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 4px;
}

.step-name {
  font-weight: 500;
}

.step-detail {
  color: #65727e;
  font-size: 11px;
}

.step-item.is-tool_call .step-detail {
  color: #24a06b;
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
