<template>
  <div class="report-page page-content">
    <div class="report-heading"><div><span class="eyebrow">REPORT WORKBENCH</span><h1>辅助影像报告</h1><p>基于当前病例结构化数据与知识依据生成可审阅的报告草稿。</p></div><el-tag type="info" effect="plain">辅助决策 · 非最终诊断</el-tag></div>

    <el-card class="report-card" shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div><strong>报告草稿</strong><small>生成后请由医生审阅并确认</small></div>
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
      <el-empty v-else description="暂无报告，请先完成影像检测后生成报告草稿。" :image-size="88" />
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
.page-content { width: min(1120px, 100%); margin: 0 auto; }.report-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin:8px 0 20px; }.eyebrow { color:#688094; font-size:10px; font-weight:700; letter-spacing:.1em; }.report-heading h1 { margin:6px 0; font-size:28px; letter-spacing:-.03em; }.report-heading p { margin:0; color:#66798a; font-size:13px; }.report-card { border:1px solid #d7e0e6; border-radius:10px; }.report-card :deep(.el-card__header) { background:#f7faf9; }.report-card :deep(.el-card__header) > div > div { display:flex; flex-direction:column; gap:3px; }.report-card :deep(.el-card__header) small { color:#718494; font-size:11px; }
.report-content {
  line-height: 1.8;
  font-size: 14px;
  color: #263946;
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
@media (max-width: 700px) { .report-heading { flex-direction:column; }.report-heading > .el-tag { align-self:flex-start; }.report-card :deep(.el-card__header > div) { align-items:flex-start !important; flex-direction:column; gap:12px; }.report-card :deep(.el-space) { flex-wrap:wrap; } }
</style>
