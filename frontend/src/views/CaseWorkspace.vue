<template>
  <div class="workstation-page">
    <header class="study-header">
      <div class="study-identity">
        <span class="eyebrow">CURRENT STUDY</span>
        <div class="study-title-row">
          <h1>{{ currentFile?.name || caseStore.caseContext?.image_info?.filename || caseStore.caseContext?.image_info?.image_name || '当前病例' }}</h1>
          <el-tag effect="plain" type="info">CT</el-tag>
          <el-tag :type="analysisTagType" effect="light">{{ analysisLabel }}</el-tag>
        </div>
        <p>{{ patientLabel }} · {{ noduleList.length ? `已发现 ${noduleList.length} 个结节` : '等待上传影像进行分析' }}</p>
      </div>
      <div class="study-actions">
        <el-button @click="$router.push('/sessions')">病例记录</el-button>
        <el-button type="primary" @click="$router.push('/report')">报告工作台</el-button>
      </div>
    </header>

    <el-alert
      v-if="analysisError"
      class="analysis-alert"
      type="error"
      :title="analysisError"
      show-icon
      :closable="true"
      @close="analysisError = ''"
    />

    <main class="workstation-grid">
      <aside class="study-rail">
        <section class="rail-section">
          <div class="rail-heading"><span>检查与发现</span><small>PRIMARY INPUT</small></div>
          <ImageUploader
            :current-file="currentFile"
            :upload-progress="uploadProgress"
            :detection-result="detectionSummary"
            @upload="handleFileUpload"
          />
        </section>

        <section class="rail-section findings-section">
          <div class="rail-heading"><span>AI 发现</span><el-tag size="small" type="success">{{ noduleList.length }}</el-tag></div>
          <el-empty v-if="!noduleList.length" description="暂无可复核结节" :image-size="54" />
          <button
            v-for="nodule in noduleList"
            :key="nodule.index"
            type="button"
            :class="['finding-item', { 'is-selected': selectedNoduleIndex === nodule.index }]"
            @click="selectedNoduleIndex = nodule.index"
          >
            <span class="finding-index">{{ String(nodule.index).padStart(2, '0') }}</span>
            <span class="finding-copy"><strong>结节 {{ nodule.index }}</strong><small>{{ formatDiameter(nodule.diameter) }} · 置信度 {{ formatScore(nodule.score) }}</small></span>
            <span class="finding-arrow">›</span>
          </button>
        </section>
      </aside>

      <section class="analysis-stage" aria-label="影像分析画布">
        <div class="stage-toolbar">
          <div><span class="stage-kicker">ANALYSIS CANVAS</span><strong>影像分析区</strong></div>
          <span class="canvas-note">当前版本展示 AI 分析状态与结构化发现</span>
        </div>

        <div class="analysis-canvas">
          <div class="canvas-grid" />
          <template v-if="currentFile">
            <div class="study-stamp"><span>CT</span><strong>{{ currentFile.name }}</strong><small>{{ formatFileSize(currentFile.size) }}</small></div>
            <div v-if="currentFile.status === 'analyzing'" class="canvas-state"><el-icon class="is-loading"><Loading /></el-icon><strong>Martin 正在分析影像</strong><span>正在执行结节检测；大型 CT 通常需要数分钟。</span></div>
            <div v-else-if="currentFile.status === 'error'" class="canvas-state canvas-state--error"><el-icon><CircleCloseFilled /></el-icon><strong>影像分析未完成</strong><span>{{ analysisError || '请检查文件格式和本机服务后重新上传。' }}</span></div>
            <div v-else-if="selectedNodule" class="selected-finding-card">
              <span>SELECTED FINDING</span><strong>结节 {{ selectedNodule.index }}</strong>
              <div class="selected-measures"><b>{{ formatDiameter(selectedNodule.diameter) }}</b><small>最大直径</small><b>{{ formatScore(selectedNodule.score) }}</b><small>AI 置信度</small></div>
              <p v-if="selectedNodule.center">坐标：{{ formatPoint(selectedNodule.center) }}</p>
            </div>
            <div v-else class="canvas-state"><el-icon><CircleCheckFilled /></el-icon><strong>影像分析已准备完成</strong><span>从左侧选择结节，查看诊断信息链。</span></div>
          </template>
          <div v-else class="canvas-empty"><el-icon><Picture /></el-icon><strong>等待 CT 影像</strong><span>从左侧上传 .nii 或 .nii.gz 文件开始分析。</span></div>
        </div>

        <div class="stage-footer"><span>影像渲染与切片定位将在后续阅片能力中提供</span><span>{{ currentFile ? analysisLabel : '尚未加载检查' }}</span></div>
      </section>

      <aside class="diagnostic-rail">
        <section class="diagnostic-chain">
          <div class="rail-heading"><span>诊断信息链</span><small>CLINICAL REVIEW</small></div>
          <div v-if="selectedNodule" class="chain-card chain-card--finding">
            <span class="chain-step">01 · 检测发现</span>
            <h2>结节 {{ selectedNodule.index }}</h2>
            <div class="chain-grid"><div><span>最大直径</span><strong>{{ formatDiameter(selectedNodule.diameter) }}</strong></div><div><span>置信度</span><strong>{{ formatScore(selectedNodule.score) }}</strong></div></div>
            <p v-if="selectedNodule.dimensions">三维尺寸：{{ formatPoint(selectedNodule.dimensions) }}</p>
          </div>
          <div v-else class="chain-card chain-card--empty"><span class="chain-step">01 · 检测发现</span><p>上传影像并选择一个结节后，在此查看结构化测量与诊断依据。</p></div>
        </section>

        <PatientContextPanel :case-context="caseStore.caseContext" />
        <KnowledgeSummaryPanel :knowledge-summary="caseStore.caseContext?.knowledge_summary || ''" @view-original="handleViewOriginal" />
        <div class="report-cta"><span>下一步</span><strong>生成辅助影像报告</strong><el-button type="primary" plain @click="$router.push('/report')">打开报告工作台</el-button></div>
      </aside>
    </main>

    <button class="copilot-launcher" type="button" :aria-expanded="copilotOpen" @click="copilotOpen = true"><el-icon><ChatDotRound /></el-icon><span>Martin Copilot</span><small>{{ chatStore.messages.length - 1 > 0 ? `${chatStore.messages.length - 1} 条对话` : '开始问诊' }}</small></button>

    <el-drawer v-model="copilotOpen" :direction="copilotDirection" :size="copilotSize" :with-header="false" class="copilot-drawer">
      <section class="copilot-panel">
        <header class="copilot-header"><div><span class="eyebrow">MARTIN COPILOT</span><h2>病例辅助对话</h2><p>{{ selectedNodule ? `正在查看结节 ${selectedNodule.index}` : '可结合当前病例继续追问' }}</p></div><el-button circle text aria-label="关闭 Martin Copilot" @click="copilotOpen = false">×</el-button></header>
        <div ref="chatContainer" class="copilot-messages" aria-live="polite">
          <article v-for="(message, index) in chatStore.messages" :key="index" :class="['copilot-message', `is-${message.role}`]"><span>{{ message.role === 'user' ? '医生' : 'Martin' }}</span><p>{{ message.content }}</p></article>
          <div v-if="chatStore.loading" class="copilot-thinking"><el-icon class="is-loading"><Loading /></el-icon>Martin 正在分析…</div>
        </div>
        <AgentTimeline :events="chatStore.timeline" />
        <div class="copilot-composer">
          <div v-if="selectedFile" class="attachment-chip"><span>{{ selectedFile.name }}</span><el-button link size="small" @click="clearSelectedFile">移除</el-button></div>
          <div class="composer-row"><el-upload :show-file-list="false" :auto-upload="false" accept=".nii,.nii.gz" :on-change="handleFileSelect"><el-button :icon="Paperclip" circle aria-label="上传 CT 附件" /></el-upload><el-input v-model="inputMessage" type="textarea" :rows="2" resize="none" placeholder="询问当前病例、结节或报告建议…" :disabled="chatStore.loading" @keydown.enter.exact.prevent="handleSend" /><el-button type="primary" :loading="chatStore.loading" :disabled="!inputMessage.trim()" @click="handleSend">发送</el-button></div>
        </div>
      </section>
    </el-drawer>
    <KnowledgeDocumentDrawer v-model:visible="docDrawerVisible" :filename="docDrawerFilename" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChatDotRound, CircleCheckFilled, CircleCloseFilled, Loading, Paperclip, Picture } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import AgentTimeline from '../components/AgentTimeline.vue'
import ImageUploader from '../components/ImageUploader.vue'
import KnowledgeDocumentDrawer from '../components/KnowledgeDocumentDrawer.vue'
import KnowledgeSummaryPanel from '../components/KnowledgeSummaryPanel.vue'
import PatientContextPanel from '../components/PatientContextPanel.vue'
import { analyzeImage, uploadImage } from '../api'
import { useCaseStore } from '../stores/caseStore'
import { useChatStore } from '../stores/chatStore'

type Nodule = { index: number; diameter: number; score: number; center?: Record<string, number>; dimensions?: Record<string, number> }

const caseStore = useCaseStore()
const chatStore = useChatStore()
const selectedFile = ref<File | null>(null)
const currentFile = computed({
  get: () => caseStore.currentFile,
  set: (file) => { caseStore.currentFile = file },
})
const uploadProgress = computed({
  get: () => caseStore.uploadProgress,
  set: (progress) => { caseStore.uploadProgress = progress },
})
const analysisError = computed({
  get: () => caseStore.analysisError,
  set: (message) => { caseStore.analysisError = message },
})
const inputMessage = ref('')
const selectedNoduleIndex = ref<number | null>(null)
const copilotOpen = ref(false)
const compactViewport = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
const docDrawerVisible = ref(false)
const docDrawerFilename = ref('')

const noduleList = computed<Nodule[]>(() => Array.isArray(caseStore.caseContext?.nodules) ? caseStore.caseContext.nodules as Nodule[] : [])
const detectionSummary = computed(() => noduleList.value.length ? { total_nodules: noduleList.value.length, nodules: noduleList.value } : null)
const selectedNodule = computed(() => noduleList.value.find((item) => item.index === selectedNoduleIndex.value) || null)
const patientLabel = computed(() => { const info = caseStore.caseContext?.patient_info; if (!info) return '未录入患者风险信息'; return [info.gender, info.age ? `${info.age} 岁` : ''].filter(Boolean).join(' · ') || '患者信息待完善' })
const analysisLabel = computed(() => currentFile.value?.status === 'analyzing' ? '分析中' : currentFile.value?.status === 'done' ? '分析完成' : currentFile.value?.status === 'error' ? '分析失败' : currentFile.value ? '影像已加载' : '未加载影像')
const analysisTagType = computed(() => currentFile.value?.status === 'analyzing' ? 'warning' : currentFile.value?.status === 'done' ? 'success' : currentFile.value?.status === 'error' ? 'danger' : 'info')
const copilotDirection = computed(() => compactViewport.value ? 'btt' : 'rtl')
const copilotSize = computed(() => compactViewport.value ? '78vh' : 'min(430px, 38vw)')

function updateViewport() { compactViewport.value = window.innerWidth <= 820 }
onMounted(() => { updateViewport(); window.addEventListener('resize', updateViewport) })
onBeforeUnmount(() => window.removeEventListener('resize', updateViewport))
watch(noduleList, (items) => { if (items.length && !items.some((item) => item.index === selectedNoduleIndex.value)) selectedNoduleIndex.value = items[0].index }, { immediate: true })
watch(() => [chatStore.messages.length, chatStore.loading], async () => { await nextTick(); if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight })

async function handleFileSelect(file: UploadFile) { if (!file.raw) return; selectedFile.value = file.raw; await handleFileUpload(file.raw) }
async function handleFileUpload(file: File) {
  try {
    analysisError.value = ''
    currentFile.value = { name: file.name, size: file.size, status: 'uploading' }; uploadProgress.value = 0
    const response = await uploadImage(file, (progress) => { uploadProgress.value = progress })
    currentFile.value = { name: file.name, size: file.size, status: 'analyzing' }
    const detection = await analyzeImage(response.data.object_name, chatStore.sessionId)
    caseStore.detectResult = detection.data
    caseStore.updateCaseContext(detection.data.case_context)
    currentFile.value = { name: file.name, size: file.size, status: 'done' }
    selectedFile.value = null
    uploadProgress.value = 0
  } catch (error) {
    const apiError = error as { response?: { data?: { detail?: string } }; message?: string }
    analysisError.value = apiError.response?.data?.detail || apiError.message || '影像上传或分析失败，请稍后重试。'
    currentFile.value = { name: file.name, size: file.size, status: 'error' }
    selectedFile.value = null
    uploadProgress.value = 0
    console.error('影像上传或分析失败', error)
  }
}
function clearSelectedFile() { selectedFile.value = null }
async function handleSend() { if (!inputMessage.value.trim() || chatStore.loading) return; const message = inputMessage.value; inputMessage.value = ''; await chatStore.sendMessage(message, caseStore.caseContext as Record<string, any>) }
function handleViewOriginal(filename: string) { docDrawerFilename.value = filename; docDrawerVisible.value = true }
function formatDiameter(value: number) { return Number.isFinite(value) ? `${value.toFixed(1)} mm` : '--' }
function formatScore(value: number) { return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '--' }
function formatPoint(value: Record<string, number>) { return Object.entries(value).filter(([, item]) => typeof item === 'number').map(([key, item]) => `${key}: ${item}`).join(' · ') || '--' }
function formatFileSize(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.round(value / 1024)} KB` }
</script>

<style scoped>
.workstation-page { min-height: calc(100vh - 58px); color: #1b2b38; }.analysis-alert { margin:0 0 14px; }
.study-header { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:14px; padding:4px 2px 14px; border-bottom:1px solid #d4dde4; }.eyebrow,.stage-kicker,.chain-step { color:#6e8495; font-size:10px; font-weight:700; letter-spacing:.1em; }.study-title-row { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:5px; }.study-title-row h1 { max-width:720px; margin:0; overflow:hidden; font-size:24px; letter-spacing:-.025em; text-overflow:ellipsis; white-space:nowrap; }.study-identity p { margin:5px 0 0; color:#66798a; font-size:13px; }.study-actions { display:flex; flex:0 0 auto; gap:8px; }
.workstation-grid { display:grid; grid-template-columns:minmax(230px, .7fr) minmax(430px, 1.65fr) minmax(255px, .78fr); gap:12px; align-items:stretch; min-height:calc(100vh - 150px); }.study-rail,.diagnostic-rail { display:flex; min-width:0; flex-direction:column; gap:12px; }.rail-section,.diagnostic-chain,.report-cta { padding:14px; background:#fff; border:1px solid #d7e0e6; border-radius:10px; box-shadow:0 1px 2px rgba(23,33,43,.025); }.rail-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:12px; color:#304558; font-size:13px; font-weight:700; }.rail-heading small { color:#8797a5; font-size:9px; letter-spacing:.08em; }.findings-section { flex:1; }.finding-item { display:flex; width:100%; align-items:center; gap:9px; margin-top:5px; padding:10px 6px; color:inherit; text-align:left; background:transparent; border:0; border-top:1px solid #edf1f3; cursor:pointer; }.finding-item:hover,.finding-item.is-selected { margin-left:-6px; width:calc(100% + 12px); padding-right:12px; padding-left:12px; background:#e8f2ee; border-radius:7px; }.finding-index { color:#25805a; font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }.finding-copy { display:flex; min-width:0; flex:1; flex-direction:column; gap:3px; }.finding-copy strong { font-size:13px; }.finding-copy small { overflow:hidden; color:#708293; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }.finding-arrow { color:#8ba0af; font-size:23px; }
.analysis-stage { display:flex; min-width:0; flex-direction:column; overflow:hidden; background:#172431; border:1px solid #0e1821; border-radius:12px; box-shadow:0 12px 28px rgba(17,30,42,.12); }.stage-toolbar,.stage-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:13px 16px; color:#e8eff3; background:#1e2e3d; }.stage-toolbar strong { display:block; margin-top:3px; font-size:15px; }.stage-toolbar .stage-kicker { color:#8fb2c8; }.canvas-note,.stage-footer { color:#9fb5c4; font-size:11px; }.analysis-canvas { position:relative; display:flex; min-height:440px; flex:1; align-items:center; justify-content:center; overflow:hidden; }.canvas-grid { position:absolute; inset:0; opacity:.32; background-image:linear-gradient(rgba(153,187,202,.14) 1px,transparent 1px),linear-gradient(90deg,rgba(153,187,202,.14) 1px,transparent 1px); background-size:32px 32px; }.canvas-empty,.canvas-state { z-index:1; display:flex; max-width:310px; align-items:center; flex-direction:column; gap:9px; color:#dbe7ec; text-align:center; }.canvas-empty .el-icon { color:#77b69a; font-size:48px; }.canvas-empty strong,.canvas-state strong { font-size:17px; }.canvas-empty span,.canvas-state span { color:#99adba; font-size:13px; line-height:1.6; }.canvas-state .el-icon { color:#75c49e; font-size:28px; }.canvas-state--error .el-icon { color:#ff9a91; }.canvas-state--error span { color:#f0bbb7; }.study-stamp { position:absolute; top:18px; left:18px; z-index:1; display:flex; max-width:55%; flex-direction:column; gap:4px; color:#dce8ed; }.study-stamp span { color:#78bd9d; font-size:11px; font-weight:700; letter-spacing:.1em; }.study-stamp strong { overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }.study-stamp small { color:#94adbd; }.selected-finding-card { z-index:1; width:min(320px,80%); padding:20px; color:#e8f2ee; background:rgba(28,54,56,.88); border:1px solid #5d9c80; border-radius:10px; box-shadow:0 16px 30px rgba(0,0,0,.22); }.selected-finding-card > span { color:#9ed4b8; font-size:10px; letter-spacing:.1em; }.selected-finding-card > strong { display:block; margin-top:6px; font-size:22px; }.selected-measures { display:grid; grid-template-columns:1fr 1fr; gap:3px 16px; margin-top:18px; }.selected-measures b { font-size:19px; }.selected-measures small,.selected-finding-card p { color:#b5c9c2; font-size:11px; }.selected-finding-card p { margin:16px 0 0; line-height:1.5; }.stage-footer { border-top:1px solid #2d4150; background:#172431; }
.chain-card { padding:13px; background:#f7faf9; border:1px solid #d9e5df; border-radius:8px; }.chain-card--empty { color:#738493; font-size:12px; line-height:1.65; }.chain-card h2 { margin:7px 0 14px; font-size:19px; }.chain-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }.chain-grid div { display:flex; flex-direction:column; gap:4px; padding:8px; background:#fff; border-radius:6px; }.chain-grid span { color:#748696; font-size:10px; }.chain-grid strong { font-size:14px; }.chain-card p { margin:12px 0 0; color:#657987; font-size:11px; line-height:1.5; }.diagnostic-rail :deep(.context-card) { box-shadow:0 1px 2px rgba(23,33,43,.025); }.report-cta { display:flex; flex-direction:column; align-items:flex-start; gap:7px; }.report-cta span { color:#708494; font-size:11px; }.report-cta strong { font-size:14px; }.report-cta .el-button { margin-top:3px; }
.copilot-launcher { position:fixed; right:24px; bottom:24px; z-index:10; display:flex; align-items:center; gap:8px; padding:11px 14px; color:#fff; background:#147551; border:1px solid #0e5d3f; border-radius:9px; box-shadow:0 10px 26px rgba(10,62,42,.25); cursor:pointer; }.copilot-launcher .el-icon { font-size:18px; }.copilot-launcher span { font-weight:700; }.copilot-launcher small { padding-left:8px; color:#bde4d0; border-left:1px solid rgba(255,255,255,.25); }.copilot-panel { display:flex; height:100%; flex-direction:column; background:#f4f7f8; }.copilot-header { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; padding:22px 20px 16px; background:#102130; color:#fff; }.copilot-header .eyebrow { color:#92c6af; }.copilot-header h2 { margin:5px 0; font-size:19px; }.copilot-header p { margin:0; color:#b9cad4; font-size:12px; }.copilot-header .el-button { color:#dce6eb; font-size:20px; }.copilot-messages { display:flex; flex:1; flex-direction:column; gap:12px; padding:16px; overflow-y:auto; }.copilot-message { display:flex; width:min(90%,350px); flex-direction:column; gap:5px; }.copilot-message.is-user { align-self:flex-end; align-items:flex-end; }.copilot-message > span { color:#708494; font-size:10px; font-weight:700; }.copilot-message p { margin:0; padding:10px 12px; color:#263946; font-size:13px; line-height:1.65; background:#fff; border:1px solid #dce5e9; border-radius:8px; white-space:pre-wrap; overflow-wrap:anywhere; }.copilot-message.is-user p { background:#dff0e7; border-color:#bdddc9; }.copilot-thinking { display:flex; align-items:center; gap:7px; color:#5d7483; font-size:12px; }.copilot-composer { padding:12px; background:#fff; border-top:1px solid #d8e1e6; }.attachment-chip { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; padding:6px 8px; color:#33634c; font-size:12px; background:#ebf5ef; border-radius:5px; }.composer-row { display:flex; align-items:flex-end; gap:7px; }.composer-row .el-input { flex:1; }
@media (max-width:1180px) { .workstation-grid { grid-template-columns:minmax(225px,.75fr) minmax(410px,1.5fr); }.diagnostic-rail { display:grid; grid-column:1 / -1; grid-template-columns:repeat(3,minmax(0,1fr)); align-items:start; }.diagnostic-chain { grid-row:span 2; }.diagnostic-rail :deep(.case-context-panel) { display:contents; }.diagnostic-rail :deep(.context-card) { min-width:0; }.report-cta { min-height:120px; }.analysis-canvas { min-height:470px; } }
@media (max-width:820px) { .workstation-page { min-height:0; }.study-header { align-items:flex-start; flex-direction:column; }.study-title-row h1 { max-width:100%; font-size:21px; }.study-actions { width:100%; }.study-actions .el-button { flex:1; }.workstation-grid { display:flex; flex-direction:column; min-height:0; }.analysis-stage { min-height:500px; order:-1; }.analysis-canvas { min-height:400px; }.diagnostic-rail { display:flex; }.copilot-launcher { right:14px; bottom:14px; }.copilot-launcher small { display:none; } }
</style>
