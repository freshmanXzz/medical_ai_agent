<template>
  <div class="knowledge-page page-content">
    <div class="page-heading">
      <div>
        <span class="eyebrow">ADMINISTRATION TOOL</span>
        <h1>知识库管理</h1>
        <p>维护 Martin 的循证资料来源；该页面用于资料管理与检索核验。</p>
      </div>
      <el-button v-if="activeTab === 'documents'" :loading="rebuilding" @click="handleRebuild">重建全部向量</el-button>
    </div>

    <el-tabs v-model="activeTab" class="knowledge-tabs">
      <el-tab-pane label="文档管理" name="documents">
        <el-alert
          title="重建会重新索引项目内置指南和所有已上传资料，期间检索结果可能短暂不可用。"
          type="info"
          :closable="false"
          show-icon
        />

        <section class="upload-card">
          <h2>上传资料</h2>
          <el-upload
            drag
            :show-file-list="false"
            :auto-upload="false"
            accept=".md,.txt,.pdf,.docx,.csv"
            :on-change="handleUpload"
            :disabled="uploading"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>拖拽文件到此处，或点击选择上传</div>
            <template #tip><small>支持 Markdown、TXT、PDF、Word、CSV；上传后自动向量化。</small></template>
          </el-upload>
          <el-progress v-if="uploading" :percentage="100" :indeterminate="true" :show-text="false" />
        </section>

        <section class="documents-card">
          <div class="section-heading">
            <h2>资料列表 <small>{{ documents.length }} 份</small></h2>
            <el-button text :loading="loading" @click="loadDocuments">刷新</el-button>
          </div>
          <el-table v-loading="loading" :data="documents" empty-text="暂无知识库资料">
            <el-table-column prop="filename" label="文件名" min-width="220" />
            <el-table-column label="来源" width="110">
              <template #default="{ row }"><el-tag :type="row.source_type === 'builtin' ? 'info' : 'success'">{{ row.source_type === 'builtin' ? '内置' : '上传' }}</el-tag></template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template>
            </el-table-column>
            <el-table-column label="向量块" width="100"><template #default="{ row }">{{ row.chunk_count ?? '—' }}</template></el-table-column>
            <el-table-column label="上传时间" min-width="170"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }"><el-button v-if="row.deletable" type="danger" link @click="handleDelete(row)">删除</el-button><span v-else class="readonly">只读</span></template>
            </el-table-column>
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="检索测试" name="search">
        <section class="search-card">
          <div class="search-intro">
            <h2>检索测试</h2>
            <p>直接查询 Agent 共用的向量库，用于核验 RAG 实际召回的资料片段。</p>
          </div>
          <div class="search-controls">
            <el-input
              v-model="searchQuery"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              maxlength="1000"
              show-word-limit
              placeholder="例如：左肺上叶磨玻璃结节的分叶征判断"
              :disabled="searching"
            />
            <el-button type="primary" :loading="searching" @click="handleSearch">测试检索</el-button>
          </div>

          <el-alert v-if="searchError" :title="searchError" type="error" :closable="false" show-icon class="search-error" />

          <div v-if="searchAttempted && !searchError" class="search-results">
            <div class="section-heading">
              <h2>召回结果 <small>Top 5 · {{ searchResults.length }} 条</small></h2>
            </div>
            <el-empty v-if="searchResults.length === 0" description="未检索到相关向量片段" />
            <article v-for="result in searchResults" :key="`${result.document_id}-${result.rank}`" class="search-result">
              <div class="result-heading">
                <div>
                  <strong>Top {{ result.rank }} · {{ result.source || '未标记来源' }}</strong>
                  <div class="result-meta">
                    <el-tag size="small" :type="result.source_type === 'upload' ? 'success' : 'info'">{{ result.source_type === 'upload' ? '上传资料' : '内置资料' }}</el-tag>
                    <span>相似度 {{ formatScore(result.score) }}</span>
                  </div>
                </div>
                <el-button v-if="isLongResult(result.content)" text type="primary" @click="toggleResult(result.rank)">{{ expandedResultRank === result.rank ? '收起' : '展开完整片段' }}</el-button>
              </div>
              <p class="result-content">{{ displayResultContent(result.rank, result.content) }}</p>
              <p v-if="result.document_id" class="result-document-id">文档 ID：{{ result.document_id }}</p>
            </article>
          </div>
        </section>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import {
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  rebuildKnowledgeBase,
  searchKnowledgeVectors,
  uploadKnowledgeDocument,
  type KnowledgeDocumentSummary,
  type KnowledgeSearchResult,
} from '../api'

const documents = ref<KnowledgeDocumentSummary[]>([])
const activeTab = ref<'documents' | 'search'>('documents')
const loading = ref(false)
const uploading = ref(false)
const rebuilding = ref(false)
const searchQuery = ref('')
const searching = ref(false)
const searchAttempted = ref(false)
const searchError = ref('')
const searchResults = ref<KnowledgeSearchResult[]>([])
const expandedResultRank = ref<number | null>(null)
const RESULT_PREVIEW_LENGTH = 420

async function loadDocuments() {
  loading.value = true
  try { documents.value = (await listKnowledgeDocuments()).data.documents } catch { ElMessage.error('读取知识库列表失败') } finally { loading.value = false }
}

async function handleUpload(file: UploadFile) {
  if (!file.raw) return
  uploading.value = true
  try { await uploadKnowledgeDocument(file.raw); ElMessage.success('资料已上传并完成向量化'); await loadDocuments() } catch (error: any) { ElMessage.error(error.response?.data?.detail || '资料上传或向量化失败') } finally { uploading.value = false }
}

async function handleDelete(document: KnowledgeDocumentSummary) {
  try {
    await ElMessageBox.confirm(`将删除“${document.filename}”及其全部向量，是否继续？`, '删除知识库资料', { type: 'warning' })
    await deleteKnowledgeDocument(document.document_id)
    ElMessage.success('资料及关联向量已删除')
    await loadDocuments()
  } catch (error: any) { if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败') }
}

async function handleRebuild() {
  try {
    await ElMessageBox.confirm('将清空并重新构建全部知识库向量，是否继续？', '重建知识库', { type: 'warning' })
    rebuilding.value = true
    const result = (await rebuildKnowledgeBase()).data
    ElMessage.success(`已重建 ${result.documents} 份资料、${result.chunks} 个向量块`)
    await loadDocuments()
  } catch (error: any) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error.response?.data?.detail || '重建失败') } finally { rebuilding.value = false }
}

async function handleSearch() {
  const query = searchQuery.value.trim()
  if (!query) {
    ElMessage.warning('请输入要测试的检索文本')
    return
  }

  searching.value = true
  searchAttempted.value = false
  searchError.value = ''
  expandedResultRank.value = null
  try {
    const response = await searchKnowledgeVectors(query)
    searchResults.value = response.data.results
    searchAttempted.value = true
  } catch (error: any) {
    searchResults.value = []
    searchError.value = error.response?.data?.detail || '向量检索失败，请稍后重试'
  } finally {
    searching.value = false
  }
}

function isLongResult(content: string) { return content.length > RESULT_PREVIEW_LENGTH }
function displayResultContent(rank: number, content: string) {
  return expandedResultRank.value === rank || !isLongResult(content)
    ? content
    : `${content.slice(0, RESULT_PREVIEW_LENGTH)}…`
}
function toggleResult(rank: number) { expandedResultRank.value = expandedResultRank.value === rank ? null : rank }
function formatScore(score: number) { return `${(score * 100).toFixed(1)}%` }
function statusLabel(status: string) { return ({ ready: '已就绪', indexing: '向量化中', failed: '失败' } as Record<string, string>)[status] || status }
function statusType(status: string) { return status === 'ready' ? 'success' : status === 'failed' ? 'danger' : 'warning' }
function formatDate(value: string) { return value ? new Date(value).toLocaleString('zh-CN') : '项目内置' }
onMounted(loadDocuments)
</script>

<style scoped>
.page-content { width: min(1120px, 100%); margin: 0 auto; }
.page-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-heading h1, .section-heading h2 { margin: 0; }.page-heading h1 { margin-top:5px; font-size:28px; letter-spacing:-.03em; }.page-heading p { color: #6b7785; }.eyebrow { color:#688094; font-size:10px; font-weight:700; letter-spacing:.1em; }
.knowledge-tabs { margin-top: 18px; }
.knowledge-tabs :deep(.el-tab-pane) > .el-alert { margin-top: 2px; }
.upload-card, .documents-card { margin-top: 18px; padding: 20px; background: #fff; border: 1px solid #dfe4e8; border-radius: 6px; }
.upload-card h2, .documents-card h2 { margin: 0 0 14px; font-size: 18px; }
.upload-icon { margin-bottom: 10px; font-size: 34px; color: #24a06b; }
.upload-card :deep(.el-upload), .upload-card :deep(.el-upload-dragger) { width: 100%; }
.upload-card :deep(.el-upload-dragger) { padding: 28px 16px; }
.upload-card .el-progress { margin-top: 12px; }
.section-heading h2 small { color: #7b8792; font-size: 13px; font-weight: 400; }
.readonly { color: #89939d; font-size: 13px; }
.search-card { padding: 20px; background: #fff; border: 1px solid #dfe4e8; border-radius: 6px; }
.search-intro h2 { margin: 0; font-size: 18px; }
.search-intro p { margin: 8px 0 16px; color: #6b7785; }
.search-controls { display: flex; align-items: flex-end; gap: 12px; }
.search-controls .el-input { flex: 1; }
.search-controls .el-button { min-width: 96px; }
.search-error { margin-top: 16px; }
.search-results { margin-top: 24px; }
.search-result { margin-top: 12px; padding: 16px; border: 1px solid #dbe7f5; border-radius: 6px; background: #f7fbff; }
.result-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.result-meta { display: flex; align-items: center; gap: 8px; margin-top: 8px; color: #587086; font-size: 13px; }
.result-content { margin: 14px 0 0; color: #344250; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.result-document-id { margin: 12px 0 0; color: #7b8792; font-size: 12px; word-break: break-all; }
@media (max-width: 700px) { .page-heading { align-items: flex-start; flex-direction: column; } }
@media (max-width: 700px) { .search-controls { align-items: stretch; flex-direction: column; } .search-controls .el-button { width: 100%; } }
</style>
