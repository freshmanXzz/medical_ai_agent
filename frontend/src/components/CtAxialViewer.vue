<template>
  <section class="ct-viewer" aria-label="CT 轴位辅助阅片">
    <div v-if="loadingManifest" class="viewer-state"><strong>正在加载可恢复影像…</strong></div>
    <div v-else-if="viewerError" class="viewer-state viewer-state--error"><strong>无法打开影像</strong><span>{{ viewerError }}</span></div>

    <template v-else-if="manifest">
      <header class="viewer-header">
        <div>
          <span>AXIAL REVIEW</span>
          <strong>CT 轴位辅助阅片</strong>
        </div>
        <p>{{ sliceIndex + 1 }} / {{ manifest.axial_slice_count }}</p>
      </header>

      <div class="window-controls" aria-label="窗宽窗位">
        <div class="window-presets">
          <button v-for="preset in presets" :key="preset.label" type="button" @click="applyPreset(preset.center, preset.width)">{{ preset.label }}</button>
        </div>
        <label>窗位 <input v-model.number="windowCenter" type="number" min="-1500" max="3000" step="10"></label>
        <label>窗宽 <input v-model.number="windowWidth" type="number" min="1" max="5000" step="10"></label>
      </div>

      <div :class="['viewer-layout', { 'viewer-layout--canvas-only': !showFindingPanel }]">
        <div
          class="viewer-canvas"
          tabindex="0"
          role="application"
          aria-label="CT 切片画布；可使用鼠标滚轮、方向键或翻页键翻页"
          @wheel.prevent="onWheel"
          @keydown="onKeydown"
        >
          <img v-if="sliceUrl" :src="sliceUrl" alt="当前 CT 轴位切片" @load="imageLoading = false" @error="onImageError">
          <div v-if="imageLoading" class="slice-loading">加载切片…</div>

          <svg class="nodule-overlay" :viewBox="`0 0 ${manifest.shape[0]} ${manifest.shape[1]}`" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
            <rect
              v-if="selectedBoxVisible"
              class="nodule-box"
              :x="selectedBoxVisible.x_min"
              :y="selectedBoxVisible.y_min"
              :width="Math.max(1, selectedBoxVisible.x_max - selectedBoxVisible.x_min)"
              :height="Math.max(1, selectedBoxVisible.y_max - selectedBoxVisible.y_min)"
            />
            <g v-if="selectedCenterVisible" class="crosshair">
              <line x1="0" :y1="selectedCenterVisible.y" :x2="manifest.shape[0]" :y2="selectedCenterVisible.y" />
              <line :x1="selectedCenterVisible.x" y1="0" :x2="selectedCenterVisible.x" :y2="manifest.shape[1]" />
              <circle class="crosshair-center" :cx="selectedCenterVisible.x" :cy="selectedCenterVisible.y" r="5" />
            </g>
          </svg>
          <span class="orientation orientation--top-left">R</span>
          <span class="orientation orientation--top-right">L</span>
          <span class="orientation orientation--top-center">A</span>
          <span class="orientation orientation--bottom-center">P</span>
        </div>

        <aside v-if="showFindingPanel" class="finding-panel" aria-label="检测到的结节">
          <header>检测到的结节 <span>({{ manifest.nodules.length }})</span></header>
          <p v-if="!manifest.nodules.length" class="finding-empty">未检测到可复核的结节。</p>
          <button
            v-for="nodule in manifest.nodules"
            :key="nodule.index ?? `unavailable-${nodule.diameter}`"
            type="button"
            :class="['finding-item', { 'is-selected': nodule.index === selectedNoduleIndex }]"
            :disabled="nodule.spatial_status !== 'located'"
            @click="selectNodule(nodule)"
          >
            <span class="finding-index">{{ nodule.index ?? '—' }}</span>
            <span class="finding-copy"><strong>{{ formatDiameter(nodule.diameter) }}</strong><small>{{ nodule.spatial_status === 'located' ? `检测置信度 ${formatScore(nodule.score)}` : '无法定位' }}</small></span>
          </button>
        </aside>
      </div>

      <footer class="slice-controls">
        <button type="button" aria-label="上一张切片" @click="sliceIndex = clampSlice(sliceIndex - 1)">‹</button>
        <input v-model.number="sliceIndex" type="range" min="0" :max="Math.max(0, manifest.axial_slice_count - 1)" aria-label="切片位置">
        <button type="button" aria-label="下一张切片" @click="sliceIndex = clampSlice(sliceIndex + 1)">›</button>
        <span>切片 {{ sliceIndex + 1 }} / {{ manifest.axial_slice_count }}</span>
      </footer>
      <p class="viewer-disclaimer">AI 辅助阅片，需由临床医生复核；本工具不是 DICOM 诊断级阅片器。</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getViewerAxialSliceUrl, getViewerManifest, type ViewerDisplayBox, type ViewerDisplayPoint, type ViewerManifest, type ViewerNodule } from '../api'

const props = withDefaults(defineProps<{
  threadId: string
  selectedNoduleIndex?: number | null
  selectionRequestId?: number
  showFindingPanel?: boolean
}>(), {
  selectedNoduleIndex: undefined,
  selectionRequestId: 0,
  showFindingPanel: true,
})

const emit = defineEmits<{ (event: 'select-nodule', index: number): void }>()

const manifest = ref<ViewerManifest | null>(null)
const loadingManifest = ref(false)
const imageLoading = ref(false)
const viewerError = ref('')
const sliceIndex = ref(0)
const windowCenter = ref(-600)
const windowWidth = ref(1500)
const sliceUrl = ref('')
const localSelectedNoduleIndex = ref<number | null>(null)
const presets = [
  { label: '肺窗', center: -600, width: 1500 },
  { label: '纵隔窗', center: 40, width: 400 },
  { label: '骨窗', center: 500, width: 2000 },
]
let manifestRequest = 0
let wheelFrame: number | null = null
let wheelDelta = 0

const selectedNoduleIndex = computed(() => props.selectedNoduleIndex ?? localSelectedNoduleIndex.value)
const selectedNodule = computed(() => manifest.value?.nodules.find((item) => item.index === selectedNoduleIndex.value) ?? null)
const selectedBoxVisible = computed<ViewerDisplayBox | null>(() => {
  const box = selectedNodule.value?.display_bbox
  if (!box || selectedNodule.value?.spatial_status !== 'located') return null
  return box.z_min <= sliceIndex.value && box.z_max >= sliceIndex.value ? box : null
})
const selectedCenterVisible = computed<ViewerDisplayPoint | null>(() => {
  const center = selectedNodule.value?.display_center
  return center && Math.round(center.z) === sliceIndex.value ? center : null
})

function clampSlice(value: number) {
  const max = Math.max(0, (manifest.value?.axial_slice_count ?? 1) - 1)
  return Math.min(max, Math.max(0, Math.round(value)))
}

function formatDiameter(value?: number) { return Number.isFinite(value) ? `${Number(value).toFixed(1)} mm` : '未提供尺寸' }
function formatScore(value?: number) { return Number.isFinite(value) ? `${(Number(value) * 100).toFixed(1)}%` : '未提供' }

function applyPreset(center: number, width: number) {
  windowCenter.value = center
  windowWidth.value = width
}

function loadSlice() {
  if (!manifest.value || !props.threadId) return
  sliceIndex.value = clampSlice(sliceIndex.value)
  windowCenter.value = Math.min(3000, Math.max(-1500, Number(windowCenter.value) || -600))
  windowWidth.value = Math.min(5000, Math.max(1, Number(windowWidth.value) || 1500))
  imageLoading.value = true
  sliceUrl.value = getViewerAxialSliceUrl(props.threadId, sliceIndex.value, windowCenter.value, windowWidth.value)
}

function jumpToNodule(index: number | null | undefined) {
  const nodule = manifest.value?.nodules.find((item) => item.index === index)
  const center = nodule?.display_center
  if (nodule?.spatial_status === 'located' && center) sliceIndex.value = clampSlice(center.z)
}

function selectNodule(nodule: ViewerNodule) {
  if (nodule.spatial_status !== 'located' || nodule.index === null) return
  localSelectedNoduleIndex.value = nodule.index
  emit('select-nodule', nodule.index)
  jumpToNodule(nodule.index)
}

async function loadManifest() {
  const requestId = ++manifestRequest
  manifest.value = null
  sliceUrl.value = ''
  viewerError.value = ''
  localSelectedNoduleIndex.value = null
  if (!props.threadId) return
  loadingManifest.value = true
  try {
    const response = await getViewerManifest(props.threadId)
    if (requestId !== manifestRequest) return
    manifest.value = response.data
    windowCenter.value = response.data.default_window.center
    windowWidth.value = response.data.default_window.width
    const externallySelected = response.data.nodules.find((nodule) => nodule.index === props.selectedNoduleIndex && nodule.spatial_status === 'located')
    const firstLocated = response.data.nodules.find((nodule) => nodule.spatial_status === 'located' && nodule.index !== null)
    const initialNodule = externallySelected ?? firstLocated
    if (props.selectedNoduleIndex === undefined && initialNodule?.index !== undefined) localSelectedNoduleIndex.value = initialNodule.index
    sliceIndex.value = initialNodule?.display_center ? clampSlice(initialNodule.display_center.z) : Math.floor(response.data.axial_slice_count / 2)
    loadSlice()
  } catch (error: any) {
    if (requestId !== manifestRequest) return
    viewerError.value = error.response?.data?.detail || '影像元数据加载失败，请重新上传后再试。'
  } finally {
    if (requestId === manifestRequest) loadingManifest.value = false
  }
}

function onWheel(event: WheelEvent) {
  wheelDelta += event.deltaY
  if (wheelFrame !== null) return
  wheelFrame = window.requestAnimationFrame(() => {
    sliceIndex.value = clampSlice(sliceIndex.value + (wheelDelta > 0 ? 1 : -1))
    wheelDelta = 0
    wheelFrame = null
  })
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'PageDown') {
    event.preventDefault(); sliceIndex.value = clampSlice(sliceIndex.value + 1)
  } else if (event.key === 'ArrowUp' || event.key === 'PageUp') {
    event.preventDefault(); sliceIndex.value = clampSlice(sliceIndex.value - 1)
  }
}

function onImageError() {
  imageLoading.value = false
  viewerError.value = '切片加载失败，请重新打开病例或检查影像服务。'
}

watch(() => props.threadId, loadManifest, { immediate: true })
watch(() => [props.selectedNoduleIndex, props.selectionRequestId], ([index]) => {
  if (index !== null && index !== undefined) jumpToNodule(index)
})
watch([sliceIndex, windowCenter, windowWidth], loadSlice)
onBeforeUnmount(() => { if (wheelFrame !== null) window.cancelAnimationFrame(wheelFrame) })
</script>

<style scoped>
.viewer-layout.viewer-layout--canvas-only { grid-template-columns:minmax(0,1fr); }
.ct-viewer { display:flex; min-height:0; height:100%; flex:1; flex-direction:column; color:#e8eff3; background:#111d26; }.viewer-header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 18px; background:#172733; border-bottom:1px solid #2c414e; }.viewer-header div { display:flex; flex-direction:column; gap:3px; }.viewer-header span { color:#8fb2c8; font-size:10px; font-weight:700; letter-spacing:.12em; }.viewer-header strong { font-size:15px; }.viewer-header p { margin:0; color:#bed0d9; font:600 12px ui-monospace,SFMono-Regular,Menlo,monospace; }.window-controls { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:9px 16px; background:#14232e; border-bottom:1px solid #2a3e4a; }.window-presets { display:flex; gap:5px; }.window-controls button,.window-controls input { color:#dbe7ec; background:#263b4c; border:1px solid #456072; border-radius:4px; }.window-controls button { padding:4px 8px; font-size:11px; cursor:pointer; }.window-controls button:hover { background:#31546a; }.window-controls label { display:flex; align-items:center; gap:4px; color:#acc1ce; font-size:11px; }.window-controls input { width:70px; padding:3px 5px; }.viewer-layout { display:grid; min-height:0; flex:1; grid-template-columns:minmax(0,1fr) minmax(205px,260px); background:#203039; }.viewer-canvas { position:relative; display:flex; min-height:420px; align-items:center; justify-content:center; overflow:hidden; background:#020506; outline:none; }.viewer-canvas:focus-visible { box-shadow:inset 0 0 0 2px #e94d4d; }.viewer-canvas img { display:block; width:100%; height:100%; object-fit:contain; image-rendering:auto; }.nodule-overlay { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }.nodule-box { fill:rgba(255,76,76,.05); stroke:#ff6262; stroke-width:2; vector-effect:non-scaling-stroke; }.crosshair line { stroke:#ff3838; stroke-width:1.5; vector-effect:non-scaling-stroke; }.crosshair-center { fill:rgba(255,56,56,.18); stroke:#ff3838; stroke-width:2; vector-effect:non-scaling-stroke; }.orientation { position:absolute; z-index:2; color:#d7e8e9; font:700 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace; text-shadow:0 1px 3px #000; }.orientation--top-left { top:12px; left:14px; }.orientation--top-right { top:12px; right:14px; }.orientation--top-center { top:12px; left:50%; transform:translateX(-50%); }.orientation--bottom-center { bottom:12px; left:50%; transform:translateX(-50%); }.slice-loading { position:absolute; z-index:3; padding:7px 10px; color:#c9d9df; font-size:12px; background:rgba(19,36,49,.82); border-radius:5px; }.finding-panel { padding:12px; overflow-y:auto; background:#24343d; border-left:1px solid #364b57; }.finding-panel header { margin-bottom:10px; color:#eef5f7; font-size:12px; font-weight:700; }.finding-panel header span { color:#9db8c6; }.finding-empty { color:#a9bdc8; font-size:12px; line-height:1.6; }.finding-item { display:flex; width:100%; align-items:center; gap:9px; margin:6px 0; padding:9px; color:#e8eff3; text-align:left; background:#1b2a34; border:1px solid transparent; border-radius:6px; cursor:pointer; }.finding-item:hover:not(:disabled),.finding-item.is-selected { background:#293e4a; border-color:#e25b5b; }.finding-item:disabled { opacity:.55; cursor:not-allowed; }.finding-index { display:grid; width:22px; height:22px; flex:0 0 auto; place-items:center; color:#fff; font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; background:#3a5361; border-radius:4px; }.finding-item.is-selected .finding-index { background:#d74c4c; }.finding-copy { display:flex; min-width:0; flex-direction:column; gap:3px; }.finding-copy strong { font-size:13px; }.finding-copy small { color:#b4c7d0; font-size:11px; }.slice-controls { display:flex; align-items:center; gap:9px; padding:9px 16px; color:#b2c4cd; background:#14232e; border-top:1px solid #2a3e4a; font-size:11px; }.slice-controls button { width:25px; height:24px; padding:0; color:#e8eff3; font-size:20px; line-height:1; background:#263b4c; border:1px solid #456072; border-radius:4px; cursor:pointer; }.slice-controls input { flex:1; accent-color:#e55555; }.viewer-disclaimer { margin:0; padding:7px 16px; color:#9db2be; font-size:10px; line-height:1.45; background:#101c25; }.viewer-state { display:flex; min-height:420px; flex:1; align-items:center; justify-content:center; flex-direction:column; gap:8px; padding:24px; color:#dbe7ec; text-align:center; background:#172431; }.viewer-state--error span { max-width:360px; color:#f0bbb7; font-size:12px; line-height:1.6; } @media (max-width:820px) { .viewer-layout { grid-template-columns:1fr; }.viewer-canvas { min-height:360px; }.finding-panel { max-height:200px; border-top:1px solid #364b57; border-left:0; }.window-controls { align-items:flex-start; flex-direction:column; } }
</style>
