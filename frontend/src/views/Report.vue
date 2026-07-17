<template>
  <div class="report-page">
    <h2>医学报告</h2>

    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>报告内容</span>
          <el-space>
            <el-select v-model="reportType" style="width: 120px">
              <el-option label="简洁版" value="brief" />
              <el-option label="详细版" value="detailed" />
              <el-option label="科研版" value="research" />
            </el-select>
            <el-button
              type="primary"
              :loading="caseStore.loading"
              @click="handleGenerate"
            >
              生成报告
            </el-button>
            <el-button @click="handleCopy">复制</el-button>
          </el-space>
        </div>
      </template>

      <div
        v-if="caseStore.reportContent"
        class="report-content"
        v-html="renderMarkdown(caseStore.reportContent)"
      />
      <div v-else style="color: #999; text-align: center; padding: 40px">
        暂无报告，请先进行影像检测后生成报告。
      </div>
    </el-card>

    <el-alert
      v-if="caseStore.error"
      :title="caseStore.error"
      type="error"
      :closable="false"
      style="margin-top: 10px"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCaseStore } from '../stores/caseStore'
import MarkdownIt from 'markdown-it'

const caseStore = useCaseStore()
const reportType = ref('detailed')
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

function renderMarkdown(text: string): string {
  return md.render(text)
}

async function handleGenerate() {
  try {
    await caseStore.runReport(reportType.value, 'zh')
    ElMessage.success('报告生成成功')
  } catch {
    // 错误已在 store 中处理
  }
}

async function handleCopy() {
  if (caseStore.reportContent) {
    try {
      await navigator.clipboard.writeText(caseStore.reportContent)
      ElMessage.success('已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败，请手动选择报告内容')
    }
  }
}
</script>

<style scoped>
.report-content {
  line-height: 1.8;
  font-size: 14px;
}
.report-content :deep(h1),
.report-content :deep(h2),
.report-content :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
}
.report-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
}
.report-content :deep(th),
.report-content :deep(td) {
  border: 1px solid #ddd;
  padding: 8px;
}
</style>
