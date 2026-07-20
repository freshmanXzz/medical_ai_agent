<template>
  <el-drawer
    :model-value="visible"
    :title="filename || '文档查看'"
    direction="rtl"
    :size="drawerSize"
    @update:model-value="handleVisibleChange"
  >
    <div v-loading="loading" class="doc-drawer-body">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />
      <div
        v-else-if="renderedContent"
        class="doc-content"
        v-html="renderedContent"
      />
      <div v-else-if="!loading" class="doc-empty">
        暂无文档内容
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { getKnowledgeDocument } from '../api'

const props = defineProps<{
  visible: boolean
  filename: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const loading = ref(false)
const error = ref('')
const renderedContent = ref('')

// drawer 宽度：50%，但最小 400px
const drawerSize = '50%'

// 监听 visible 与 filename 变化，触发文档加载
watch(
  () => [props.visible, props.filename] as const,
  ([visible, filename]) => {
    if (visible && filename) {
      loadDocument(filename)
    }
  }
)

/** 拉取知识库原文档并渲染为 HTML */
async function loadDocument(filename: string): Promise<void> {
  loading.value = true
  error.value = ''
  renderedContent.value = ''
  try {
    const res = await getKnowledgeDocument(filename)
    const content: string = res?.data?.content ?? ''
    renderedContent.value = md.render(content)
  } catch (err) {
    error.value = extractErrorMessage(err, '文档加载失败')
  } finally {
    loading.value = false
  }
}

/** 统一提取异常信息 */
function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const maybe = err as { response?: { data?: { detail?: string } }; message?: string }
    if (maybe.response?.data?.detail) return maybe.response.data.detail
    if (maybe.message) return maybe.message
  }
  return fallback
}

/** 同步父组件的 visible 状态 */
function handleVisibleChange(value: boolean): void {
  emit('update:visible', value)
}
</script>

<style scoped>
.doc-drawer-body {
  min-height: 200px;
  padding: 12px 16px;
}

.doc-content {
  color: #303133;
  font-size: 14px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.doc-content :deep(h1),
.doc-content :deep(h2),
.doc-content :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
}

.doc-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
}

.doc-content :deep(th),
.doc-content :deep(td) {
  border: 1px solid #ddd;
  padding: 8px;
}

.doc-empty {
  color: #999;
  text-align: center;
  padding: 40px 0;
}
</style>
