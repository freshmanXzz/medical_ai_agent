<template>
  <el-drawer v-model="visible" title="长期记忆" size="min(680px, 100vw)" destroy-on-close>
    <div class="memory-panel">
      <p class="intro">查看当前医生的偏好与当前患者的记忆、来源和修订历史。临床声明及纠正均为待核实信息。</p>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-alert v-if="notice" :title="notice" type="success" show-icon :closable="false" />

      <el-collapse>
        <el-collapse-item title="报告偏好 · 对当前医生的后续会话生效" name="preferences">
          <el-form label-position="top" class="preference-form" :disabled="busy || loading">
            <el-form-item label="报告顺序"><el-checkbox v-model="preference.conclusion_first">结论优先</el-checkbox></el-form-item>
            <el-form-item label="篇幅">
              <el-checkbox v-model="unlimited">不设字数上限</el-checkbox>
              <el-input-number v-if="!unlimited" v-model="wordLimit" :min="50" :max="1000" :step="50" aria-label="报告字数上限" />
            </el-form-item>
            <el-form-item label="复杂病例"><el-checkbox v-model="preference.complex_case_unlimited">本轮明确为复杂病例时，不限字数</el-checkbox></el-form-item>
            <el-form-item label="关注点（最多 10 项）"><el-select v-model="preference.focus" multiple filterable allow-create default-first-option :multiple-limit="10" placeholder="输入并选择关注点" /></el-form-item>
            <el-button type="primary" :disabled="!preferenceLoaded" :loading="busy" @click="savePreference">保存长期偏好</el-button>
          </el-form>
        </el-collapse-item>
        <el-collapse-item title="上下文预算与使用记录" name="budget">
          <BudgetPolicyPanel :active="visible" :thread-id="threadId" />
        </el-collapse-item>
      </el-collapse>

      <div class="list-toolbar">
        <el-checkbox v-model="includeInactive" :disabled="busy">显示已替代、撤回和过期记录</el-checkbox>
        <div><el-button :disabled="!threadId || busy" @click="load">刷新</el-button><el-button type="primary" plain :disabled="!threadId || busy" @click="startCreate">新增记忆</el-button></div>
      </div>
      <el-alert v-if="!threadId" title="请先打开一个病例会话，再查看和管理该患者的记忆。" type="info" :closable="false" />

      <section v-if="operation" class="editor" aria-label="记忆编辑">
        <h3>{{ operation === 'retract' ? '撤回记忆' : operation === 'revise' ? '修订记忆' : '新增记忆' }}</h3>
        <p v-if="target" class="target-id">目标 ID：{{ target.memory_id }}</p>
        <p v-if="operation === 'retract'">撤回后，该条记忆不再用于后续回答，历史仍可查阅。</p>
        <el-form label-position="top" :disabled="busy" @submit.prevent="saveMemory">
          <template v-if="operation !== 'retract'">
            <el-form-item label="记忆类型">
              <el-select v-model="form.memory_type" :disabled="operation === 'revise'">
                <el-option v-for="(label, key) in editableTypes" :key="key" :label="label" :value="key" />
              </el-select>
            </el-form-item>
            <el-form-item label="内容"><el-input v-model="form.text" type="textarea" :rows="3" maxlength="1200" show-word-limit placeholder="填写需要记住的简短信息" /></el-form-item>
            <template v-if="form.memory_type === 'clinical_claim' || form.memory_type === 'correction'">
              <el-alert title="保存为未核实声明；不会自动修改已确认的临床事实。" type="warning" :closable="false" />
              <el-checkbox v-model="hasFindingTarget">针对指定检查发现提出纠正</el-checkbox>
              <div v-if="hasFindingTarget" class="finding-fields">
                <el-form-item label="检查发现 ID"><el-input v-model="findingId" maxlength="200" placeholder="填入已有 Finding ID" /></el-form-item>
                <el-form-item label="字段"><el-select v-model="findingField"><el-option label="解剖位置" value="anatomy" /><el-option label="直径（mm）" value="diameter_mm" /><el-option label="发现类型" value="finding_type" /><el-option label="观察时间（ISO）" value="observed_at" /></el-select></el-form-item>
                <el-form-item label="建议值"><el-input v-model="proposedValue" maxlength="200" /></el-form-item>
              </div>
            </template>
            <el-form-item v-if="form.memory_type === 'task_followup' || form.memory_type === 'workflow_preference'" label="有效期至（可选）"><el-date-picker v-model="form.valid_until" type="datetime" placeholder="留空表示不设到期时间" /></el-form-item>
          </template>
          <el-form-item v-if="operation !== 'create'" label="变更原因（可选）"><el-input v-model="reason" maxlength="400" show-word-limit /></el-form-item>
          <div class="editor-actions"><el-button @click="cancelEdit">取消</el-button><el-button :type="operation === 'retract' ? 'danger' : 'primary'" :loading="busy" native-type="submit">{{ operation === 'retract' ? '确认撤回此条记忆' : '保存' }}</el-button></div>
        </el-form>
      </section>

      <div v-loading="loading" class="record-list" aria-live="polite">
        <el-empty v-if="threadId && !loading && !records.length && !error" description="暂无可查看的长期记忆" :image-size="64" />
        <article v-for="record in records" :key="record.memory_id" class="memory-card">
          <div class="card-heading"><strong>{{ typeLabel(record.memory_type) }}</strong><el-tag :type="statusType(record)" size="small">{{ statusLabel(record) }}</el-tag></div>
          <p v-if="record.memory_type === 'clinical_claim' || record.memory_type === 'correction'" class="claim-label">未核实 · 不替代已确认事实</p>
          <p class="memory-text">{{ record.text || preferenceSummary(record) }}</p>
          <p v-if="record.data.target_finding_id" class="structured-target">检查发现 {{ record.data.target_finding_id }} · {{ record.data.field }} → {{ record.data.proposed_value }}</p>
          <dl class="source-details">
            <div><dt>来源</dt><dd>{{ provenanceLabel(record) }}</dd></div>
            <div><dt>记录时间</dt><dd>{{ formatDate(record.created_at) }}</dd></div>
            <div v-if="record.valid_until"><dt>有效期至</dt><dd>{{ formatDate(record.valid_until) }}</dd></div>
            <div><dt>记忆 ID</dt><dd>{{ record.memory_id }}</dd></div>
            <div v-if="record.provenance?.actor_id"><dt>记录医生</dt><dd>{{ record.provenance.actor_id }}</dd></div>
            <div v-if="record.provenance?.message_id"><dt>消息 ID</dt><dd>{{ record.provenance.message_id }}</dd></div>
            <div v-if="record.provenance?.submission_id"><dt>提交 ID</dt><dd>{{ record.provenance.submission_id }}</dd></div>
          </dl>
          <div class="card-actions">
            <el-button link type="primary" :disabled="busy" @click="showHistory(record)">修订历史</el-button>
            <el-button v-if="isActive(record) && isEditable(record)" link type="primary" :disabled="busy" @click="startEdit(record, 'revise')">修订</el-button>
            <el-button v-if="isActive(record) && canRetract(record)" link type="danger" :disabled="busy" @click="startEdit(record, 'retract')">撤回</el-button>
          </div>
          <div v-if="historyId === record.memory_id" class="history" v-loading="historyLoading">
            <p class="history-note">历史仅供查阅，已替代或撤回的条目不会作为当前规则使用。</p>
            <article v-for="version in history" :key="version.memory_id" class="history-version">
              <strong>{{ statusLabel(version) }} · {{ formatDate(version.created_at) }}</strong>
              <p>{{ version.text || preferenceSummary(version) }}</p>
              <small>{{ provenanceLabel(version) }} · {{ version.memory_id }}</small>
              <p v-for="(event, index) in version.audit_events || []" :key="index" class="audit-event">{{ event.action === 'retract' ? '撤回' : '替代' }} · {{ event.actor_id }} · {{ formatDate(event.occurred_at) }}{{ event.reason ? ` · ${event.reason}` : '' }}</p>
            </article>
          </div>
        </article>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import BudgetPolicyPanel from './BudgetPolicyPanel.vue'
import {
  getMemoryHistory, getReportStylePreference, listMemoryRecords, retractMemoryRecord,
  reviseMemoryRecord, saveReportStylePreference, writeMemoryRecord,
  type EditableMemoryType, type MemoryFragment, type MemoryRecord, type ReportStylePreference,
} from '../api'

const props = defineProps<{ modelValue: boolean; threadId: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const visible = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })
const editableTypes: Record<EditableMemoryType, string> = {
  workflow_preference: '工作流偏好', clinical_decision: '临床决策说明',
  historical_discussion: '历史讨论', task_followup: '待办与随访',
  correction: '待核实纠正', clinical_claim: '未核实临床声明',
}
const records = ref<MemoryRecord[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const includeInactive = ref(false)
const preferenceLoaded = ref(false)
const preference = reactive<ReportStylePreference>({ conclusion_first: true, max_words: 200, complex_case_unlimited: false, focus: [] })
const unlimited = ref(false)
const wordLimit = ref(200)
const operation = ref<'create' | 'revise' | 'retract' | null>(null)
const target = ref<MemoryRecord | null>(null)
const form = reactive<MemoryFragment>({ memory_type: 'clinical_claim', text: '', valid_until: null })
const reason = ref('')
const hasFindingTarget = ref(false)
const findingId = ref('')
const findingField = ref('anatomy')
const proposedValue = ref('')
const historyId = ref('')
const history = ref<MemoryRecord[]>([])
const historyLoading = ref(false)
let loadId = 0
let historyRequestId = 0
let contextId = 0

function errorMessage(cause: unknown, fallback: string) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}
function isActive(record: MemoryRecord) { return record.status === 'active' && (!record.valid_until || Date.parse(record.valid_until) > Date.now()) }
function isEditable(record: MemoryRecord) { return Object.prototype.hasOwnProperty.call(editableTypes, record.memory_type) }
function canRetract(record: MemoryRecord) { return isEditable(record) || record.memory_type === 'doctor_preference' }
function typeLabel(type: string) { return editableTypes[type as EditableMemoryType] || ({ doctor_preference: '报告偏好', patient_fact: '患者事实', medical_observation: '医学观察', case_evolution: '病例演变' } as Record<string, string>)[type] || type }
function statusLabel(record: MemoryRecord) { return record.status === 'active' && !isActive(record) ? '已过期' : { active: '有效', superseded: '已替代', retracted: '已撤回', invalid: '已失效' }[record.status] || record.status }
function statusType(record: MemoryRecord): 'success' | 'info' | 'warning' { return isActive(record) ? 'success' : record.status === 'retracted' ? 'warning' : 'info' }
function provenanceLabel(record: MemoryRecord) { return { message: '医生会话消息', api_submission: '医生直接提交', business_event: '业务记录', legacy_unknown: '来源未完整记录（旧数据）' }[record.provenance?.kind || 'legacy_unknown'] }
function formatDate(value?: string | null) { if (!value) return '未记录'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }
function preferenceSummary(record: MemoryRecord) {
  if (record.memory_type !== 'doctor_preference') return '无文本内容'
  const data = record.data
  return [data.conclusion_first ? '结论优先' : '', data.max_words == null ? '不限字数' : `字数上限 ${data.max_words}`, data.complex_case_unlimited ? '复杂病例不限字数' : '', Array.isArray(data.focus) && data.focus.length ? `关注：${data.focus.join('、')}` : ''].filter(Boolean).join('；')
}

async function load() {
  const requestId = ++loadId
  const threadId = props.threadId
  loading.value = true
  error.value = ''
  records.value = []
  preferenceLoaded.value = false
  historyId.value = ''
  history.value = []
  historyLoading.value = false
  historyRequestId += 1
  const results = await Promise.allSettled([
    getReportStylePreference(), threadId ? listMemoryRecords(threadId, includeInactive.value) : Promise.resolve(null),
  ])
  if (requestId !== loadId) return
  const [prefs, rows] = results
  if (prefs.status === 'fulfilled') {
    const value = prefs.value.data
    Object.assign(preference, { conclusion_first: value.conclusion_first ?? true, max_words: value.max_words === undefined ? 200 : value.max_words, complex_case_unlimited: value.complex_case_unlimited ?? false, focus: value.focus || [] })
    unlimited.value = preference.max_words === null
    wordLimit.value = preference.max_words ?? 200
    preferenceLoaded.value = true
  } else error.value = errorMessage(prefs.reason, '报告偏好读取失败，请重试。')
  if (rows.status === 'fulfilled') records.value = (rows.value?.data.records || []).slice().reverse()
  else error.value = errorMessage(rows.reason, '长期记忆读取失败，请重试。')
  loading.value = false
}

function cancelEdit() { operation.value = null; target.value = null; reason.value = '' }
function startCreate() {
  target.value = null
  Object.assign(form, { memory_type: 'clinical_claim', text: '', logical_key: undefined, observed_at: undefined, valid_until: null, data: {} })
  hasFindingTarget.value = false; findingId.value = ''; findingField.value = 'anatomy'; proposedValue.value = ''; reason.value = ''
  operation.value = 'create'; error.value = ''; notice.value = ''
}
function startEdit(record: MemoryRecord, action: 'revise' | 'retract') {
  target.value = record
  Object.assign(form, { memory_type: record.memory_type as EditableMemoryType, text: record.text, logical_key: record.logical_key, observed_at: record.observed_at, valid_until: record.valid_until, data: { ...record.data } })
  hasFindingTarget.value = Boolean(record.data.target_finding_id)
  findingId.value = String(record.data.target_finding_id || ''); findingField.value = String(record.data.field || 'anatomy'); proposedValue.value = String(record.data.proposed_value ?? '')
  reason.value = ''; operation.value = action; error.value = ''; notice.value = ''
}
async function savePreference() {
  if (busy.value || !preferenceLoaded.value) return
  const requestContext = contextId
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await saveReportStylePreference({ ...preference, max_words: unlimited.value ? null : wordLimit.value })
    if (requestContext !== contextId) return
    notice.value = '报告偏好已保存。当前会话中的明确要求仍优先。'
    await load()
  } catch (cause) { if (requestContext === contextId) error.value = errorMessage(cause, '偏好保存失败，不能视为已保存。') }
  finally { if (requestContext === contextId) busy.value = false }
}
async function saveMemory() {
  if (busy.value || !props.threadId || !operation.value) return
  const requestContext = contextId
  const threadId = props.threadId
  error.value = ''; notice.value = ''
  if (operation.value !== 'retract' && !form.text.trim()) { error.value = '请填写记忆内容。'; return }
  busy.value = true
  try {
    if (operation.value === 'retract' && target.value) {
      await retractMemoryRecord(threadId, target.value.memory_id, reason.value)
      if (requestContext !== contextId) return
      notice.value = '记忆已撤回，后续回答不再应用此条记录。'
    } else {
      const data = { ...(form.data || {}) }
      delete data.target_finding_id; delete data.field; delete data.proposed_value
      if (hasFindingTarget.value && ['clinical_claim', 'correction'].includes(form.memory_type)) {
        if (!findingId.value.trim() || !proposedValue.value.trim()) throw new Error('请填写检查发现 ID 和建议值。')
        if (findingField.value === 'diameter_mm' && (!Number.isFinite(Number(proposedValue.value)) || Number(proposedValue.value) <= 0)) throw new Error('直径必须为大于 0 的数值。')
        Object.assign(data, { target_finding_id: findingId.value.trim(), field: findingField.value, proposed_value: findingField.value === 'diameter_mm' ? Number(proposedValue.value) : proposedValue.value.trim() })
      }
      const candidate: MemoryFragment = { ...form, text: form.text.trim(), data, valid_until: ['workflow_preference', 'task_followup'].includes(form.memory_type) && form.valid_until ? new Date(form.valid_until).toISOString() : null }
      const response = operation.value === 'revise' && target.value
        ? await reviseMemoryRecord(threadId, target.value.memory_id, candidate, reason.value)
        : await writeMemoryRecord(threadId, candidate)
      if (requestContext !== contextId) return
      notice.value = response.data.index_available ? '记忆已保存，来源已标注为医生直接提交。' : '记忆源记录已保存；语义索引暂不可用，可稍后重试。'
    }
    cancelEdit(); await load()
  } catch (cause) { if (requestContext === contextId) error.value = errorMessage(cause, cause instanceof Error && !('response' in cause) ? cause.message : '记忆变更失败，请重试。') }
  finally { if (requestContext === contextId) busy.value = false }
}
async function showHistory(record: MemoryRecord) {
  if (historyId.value === record.memory_id) { historyId.value = ''; historyRequestId += 1; return }
  const requestId = ++historyRequestId
  historyId.value = record.memory_id; history.value = []; historyLoading.value = true; error.value = ''
  try { const result = await getMemoryHistory(props.threadId, record.memory_id); if (requestId === historyRequestId) history.value = result.data.records }
  catch (cause) { if (requestId === historyRequestId) error.value = errorMessage(cause, '修订历史读取失败，请重试。') }
  finally { if (requestId === historyRequestId) historyLoading.value = false }
}
watch(() => [props.modelValue, props.threadId], () => {
  contextId += 1
  cancelEdit(); notice.value = ''; error.value = ''; records.value = []; history.value = []
  loading.value = false; busy.value = false; historyLoading.value = false; preferenceLoaded.value = false
  loadId += 1; historyRequestId += 1
  if (props.modelValue) void load()
}, { immediate: true })
watch(includeInactive, () => { if (props.modelValue) void load() })
onBeforeUnmount(() => { contextId += 1; loadId += 1; historyRequestId += 1 })
</script>

<style scoped>
.memory-panel { display: grid; gap: 18px; color: #243746; }
.intro, .history-note { margin: 0; color: #657787; font-size: 13px; line-height: 1.7; }
.list-toolbar, .card-heading, .editor-actions, .card-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.list-toolbar :deep(.el-checkbox) { white-space: normal; height: auto; }
.preference-form :deep(.el-select), .editor :deep(.el-select), .editor :deep(.el-date-editor) { width: 100%; }
.preference-form :deep(.el-input-number) { margin-left: 14px; }
.editor { padding: 18px; background: #f4f8fc; border: 1px solid #bed3e4; border-radius: 10px; }
.editor h3 { margin: 0 0 10px; font-size: 16px; }
.target-id { font-size: 12px; overflow-wrap: anywhere; }
.editor-actions { justify-content: flex-end; }
.finding-fields { margin-top: 12px; }
.record-list { min-height: 80px; display: grid; gap: 14px; }
.memory-card { padding: 18px; border: 1px solid #dce5eb; border-radius: 10px; background: #fff; }
.card-heading { font-size: 14px; }
.claim-label { font-size: 12px; color: #986218; }
.memory-text { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.7; }
.structured-target { font-size: 12px; overflow-wrap: anywhere; padding: 10px; background: #faf6ed; }
.source-details { margin: 14px 0; font-size: 12px; color: #657787; display: grid; gap: 6px; }
.source-details div { display: grid; grid-template-columns: 66px minmax(0, 1fr); gap: 10px; }
.source-details dd { margin: 0; overflow-wrap: anywhere; }
.card-actions { justify-content: flex-start; }
.history { margin-top: 12px; padding-top: 12px; border-top: 1px solid #e7edf1; }
.history-version { border-left: 2px solid #c7d8e3; padding-left: 12px; margin-top: 16px; font-size: 12px; overflow-wrap: anywhere; }
.history-version p { white-space: pre-wrap; line-height: 1.7; }
.history-version small, .audit-event { color: #657787; }
@media (max-width: 520px) { .memory-card, .editor { padding: 14px; }.list-toolbar { align-items: flex-start; } }
</style>
