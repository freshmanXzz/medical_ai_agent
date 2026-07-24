<template>
  <el-card v-if="knowledgeSummary" class="context-card knowledge-card" shadow="never">
    <template #header>
      <div class="card-header">
        <el-icon><Document /></el-icon>
        <span>知识摘要</span>
        <el-tag size="small" type="info" effect="dark" class="header-tag">
          {{ citations.length }} 条引用
        </el-tag>
      </div>
    </template>

    <div v-if="citations.length" class="citation-list">
      <div v-for="(item, index) in citations" :key="index" class="citation-item">
        <div class="citation-source">
          <el-icon class="source-icon"><Document /></el-icon>
          <el-tag size="small" effect="dark" type="info">{{ item.filename }}</el-tag>
        </div>
        <div class="citation-content">{{ item.excerpt }}</div>
        <el-link
          type="primary"
          :underline="false"
          class="view-link"
          @click="handleViewOriginal(item.filename)"
        >
          查看原文
        </el-link>
      </div>
    </div>
    <div v-else class="summary-text">{{ knowledgeSummary }}</div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'

/** 引用条目：来源文件名 + 内容摘要片段 */
interface CitationItem {
  filename: string
  excerpt: string
}

const props = defineProps<{
  knowledgeSummary: string
}>()

const emit = defineEmits<{
  'view-original': [filename: string]
}>()

// 解析知识摘要文本为引用条目列表
const citations = computed<CitationItem[]>(() => {
  return parseCitations(props.knowledgeSummary)
})

/** 解析知识摘要文本：按 【参考资料N】 分段，提取 来源 与 内容 */
function parseCitations(text: string): CitationItem[] {
  if (!text || !text.trim()) return []

  // 按参考资料标题分段，丢弃首段空内容
  const segments = text.split(/【参考资料\d+】/).filter((seg) => seg.trim())
  const items: CitationItem[] = []

  for (const segment of segments) {
    const sourceMatch = segment.match(/来源：(.+)/)
    const contentMatch = segment.match(/内容：(.+)/)
    if (!sourceMatch || !contentMatch) continue

    const filename = sourceMatch[1].trim()
    const fullContent = contentMatch[1].trim()
    if (!filename || !fullContent) continue

    const excerpt = fullContent.length > 80 ? fullContent.slice(0, 80) + '...' : fullContent
    items.push({ filename, excerpt })
  }

  return items
}

/** 触发查看原文事件 */
function handleViewOriginal(filename: string): void {
  emit('view-original', filename)
}
</script>

<style scoped>
.context-card {
  background: #ffffff;
  border: 1px solid #d7e0e6;
  border-radius: 10px;
}

.context-card :deep(.el-card__header) {
  padding: 10px 12px;
  background: #f7faf9;
  border-bottom: 1px solid #e2e9ed;
}

.context-card :deep(.el-card__body) {
  padding: 10px 12px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #2c7054;
  font-size: 13px;
  font-weight: 600;
}

.card-header .el-icon {
  font-size: 15px;
}

.header-tag {
  margin-left: auto;
}

.citation-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.citation-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  background: #f7faf9;
  border: 1px solid #e2e9ed;
  border-radius: 6px;
}

.citation-source {
  display: flex;
  align-items: center;
  gap: 6px;
}

.source-icon {
  color: #2c7054;
  font-size: 14px;
}

.citation-content {
  color: #314858;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.view-link {
  align-self: flex-start;
  font-size: 12px;
}

.summary-text {
  color: #314858;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
