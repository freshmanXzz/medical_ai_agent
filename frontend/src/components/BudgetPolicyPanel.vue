<template>
  <section class="budget-panel" aria-label="上下文预算">
    <div class="panel-heading">
      <p>查看本会话的上下文使用情况。系统预算由授权管理员调整，服务器执行安全上限。</p>
      <el-button size="small" :disabled="loading || busy" @click="load">刷新预算记录</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert v-if="notice" :title="notice" type="success" show-icon :closable="false" />
    <p v-if="loading" class="muted" aria-live="polite">正在读取服务器预算与权限…</p>

    <template v-if="canManage && current && draft">
      <div class="policy-status">
        <el-tag size="small">生效版本 v{{ current.version }}</el-tag>
        <el-tag size="small" :type="current.source === 'safe_default' ? 'warning' : 'success'">{{ current.source === 'safe_default' ? '安全默认配置' : '已保存配置' }}</el-tag>
        <span>当前可用输入 {{ current.policy.context_window - current.policy.reserved_output - current.policy.safety_margin }} Token</span>
      </div>
      <p class="muted">总上下文允许范围 {{ current.limits.context_min }}–{{ current.limits.context_max }} Token。以下为编辑草稿，保存后以服务器生效版本为准。</p>
      <el-form novalidate label-position="top" :disabled="loading || busy" @submit.prevent="save">
        <div class="parameter-grid">
          <el-form-item v-for="field in fields" :key="field.key" :label="field.label">
            <el-input-number v-model="draft[field.key]" :min="fieldMin(field)" :max="fieldMax(field)" :step="field.step" :precision="0" controls-position="right" :aria-label="field.label" />
            <small>{{ field.hint }}</small>
          </el-form-item>
        </div>

        <div class="quota-heading">
          <strong>任务软配额</strong>
          <el-select v-model="quotaTask" aria-label="选择预算任务" class="task-select">
            <el-option v-for="task in tasks" :key="task.key" :label="task.label" :value="task.key" />
          </el-select>
        </div>
        <p class="muted">各项权重合计为 100；空闲份额可借用，最终输入仍受统一上限限制。</p>
        <div class="quota-grid">
          <el-form-item v-for="category in categories" :key="category.key" :label="category.label">
            <el-input-number v-model="draft.category_quotas[quotaTask][category.key]" :min="0" :max="100" :precision="0" controls-position="right" :aria-label="`${taskLabel(quotaTask)}${category.label}权重`" />
          </el-form-item>
        </div>
        <p :class="['quota-total', quotaTotal === 100 ? 'muted' : 'invalid']">{{ taskLabel(quotaTask) }}权重合计：{{ quotaTotal }} / 100</p>
        <el-form-item label="变更原因">
          <el-input v-model="reason" maxlength="400" show-word-limit placeholder="说明本次调整或回退的原因" />
        </el-form-item>
        <div class="actions">
          <el-button :disabled="!dirty || loading || busy" @click="resetDraft">恢复生效参数</el-button>
          <el-button type="primary" native-type="submit" :loading="busy" :disabled="!dirty || loading || conflict">保存为新版本</el-button>
        </div>
      </el-form>

      <div class="version-history">
        <strong>策略版本与回退</strong>
        <p v-if="!versions.length" class="muted">暂无已保存的策略版本。</p>
        <template v-else>
          <div class="rollback-controls">
            <el-select v-model="targetVersion" placeholder="选择要恢复的版本" aria-label="回退目标版本" :disabled="loading || busy" class="version-select">
              <el-option v-if="current.version !== 0" label="v0 · 后端安全默认配置" :value="0" />
              <el-option v-for="version in versions" :key="version.version" :value="version.version" :label="`v${version.version} · ${formatDate(version.created_at)}`" :disabled="version.version === current.version" />
            </el-select>
            <el-button type="warning" :disabled="targetVersion === null || loading || busy || conflict" @click="rollback">回退为新版本</el-button>
          </div>
          <p v-if="selectedVersion" class="muted">将恢复 v{{ selectedVersion.version }}：总上下文 {{ selectedVersion.policy.context_window }} Token，输出预留 {{ selectedVersion.policy.reserved_output }} Token。请填写上方变更原因。</p>
          <details class="version-list">
            <summary>查看变更记录（{{ versions.length }}）</summary>
            <article v-for="version in versions" :key="version.version" class="version-entry">
              <strong>v{{ version.version }}{{ version.reverted_from != null ? ` · 回退自 v${version.reverted_from}` : '' }}</strong>
              <span>{{ version.actor_id }} · {{ formatDate(version.created_at) }}</span>
              <p>{{ version.reason || '未填写原因' }}</p>
            </article>
          </details>
        </template>
      </div>
    </template>

    <div class="trace-panel">
      <strong>当前会话预算使用</strong>
      <el-alert v-if="traceError" :title="traceError" type="error" show-icon :closable="false" />
      <p v-if="!threadId" class="muted">打开病例会话后可查看该会话的预算记录。</p>
      <p v-else-if="!loading && !trace && !traceError" class="muted">本会话暂无预算记录。完成对话或报告后刷新查看。</p>
      <template v-if="trace">
        <el-alert v-if="trace.degraded === true" title="此次请求存在未完整覆盖的证据，回答已按已处理范围降级。" type="warning" show-icon :closable="false" />
        <dl class="trace-details">
          <div v-for="row in traceDetails" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.value }}</dd></div>
        </dl>
        <p v-if="!traceDetails.length" class="muted">预算记录已返回，当前没有可展示的用量字段。</p>
        <table v-if="omissions.length" class="reason-table">
          <caption>省略或过滤原因</caption>
          <thead><tr><th scope="col">原因</th><th scope="col">条目数</th></tr></thead>
          <tbody><tr v-for="item in omissions" :key="item.reason"><td>{{ reasonLabel(item.reason) }}</td><td>{{ item.count }}</td></tr></tbody>
        </table>
        <p v-else class="muted">此次记录没有条目省略或过滤。</p>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  getBudgetPolicy, getBudgetPolicyHistory, getBudgetTrace, getCurrentDoctor,
  rollbackBudgetPolicy, saveBudgetPolicy,
  type BudgetCategory, type BudgetPolicy, type BudgetPolicyResponse,
  type BudgetPolicyVersion, type BudgetTask, type BudgetTrace,
} from '../api'

const props = defineProps<{ active: boolean; threadId: string }>()
type NumericPolicyKey = Exclude<keyof BudgetPolicy, 'category_quotas' | 'version'>
interface BudgetField { key: NumericPolicyKey; label: string; hint: string; min: number; max?: number; step: number }
const fields: BudgetField[] = [
  { key: 'context_window', label: '总上下文上限（Token）', hint: '包含输入、输出预留与安全余量', min: 1, step: 1024 },
  { key: 'reserved_output', label: '输出预留（Token）', hint: '为本次模型生成保留空间', min: 1, step: 256 },
  { key: 'safety_margin', label: '安全余量（Token）', hint: '覆盖计数误差与调用开销', min: 256, max: 8192, step: 128 },
  { key: 'minimal_background_tokens', label: '极简背景预算（Token）', hint: '每轮授权患者背景的可用份额', min: 64, max: 2048, step: 50 },
  { key: 'summary_tokens', label: '详细摘要预算（Token）', hint: '按当前任务需要注入摘要', min: 128, max: 8192, step: 100 },
  { key: 'summary_trigger_count', label: '摘要触发条数', hint: '达到规模阈值后进入摘要治理', min: 2, max: 200, step: 1 },
  { key: 'summary_trigger_tokens', label: '摘要触发量（Token）', hint: '按有效来源的规模触发治理', min: 512, step: 100 },
  { key: 'max_stage_batches', label: '分阶段最大批次', hint: '关键证据超预算时限制处理批次', min: 1, step: 1 },
  { key: 'max_stage_tokens', label: '分阶段总量上限（Token）', hint: '限制一次请求的分阶段处理资源', min: 8192, step: 1024 },
  { key: 'max_stage_seconds', label: '分阶段时限（秒）', hint: '超出时限时明确降级', min: 1, max: 120, step: 1 },
]
const tasks: { key: BudgetTask; label: string }[] = [
  { key: 'qa', label: '问答' }, { key: 'report', label: '报告' },
  { key: 'followup', label: '纵向随访' }, { key: 'default', label: '默认任务' },
]
const categories: { key: BudgetCategory; label: string }[] = [
  { key: 'history', label: '会话历史' }, { key: 'rag', label: '医学知识' },
  { key: 'memory', label: '长期记忆' }, { key: 'summary', label: '详细摘要' },
]
const current = ref<BudgetPolicyResponse | null>(null)
const draft = ref<BudgetPolicy | null>(null)
const versions = ref<BudgetPolicyVersion[]>([])
const trace = ref<BudgetTrace | null>(null)
const serverAdmin = ref(false)
const loading = ref(false)
const busy = ref(false)
const conflict = ref(false)
const error = ref('')
const traceError = ref('')
const notice = ref('')
const reason = ref('')
const quotaTask = ref<BudgetTask>('qa')
const targetVersion = ref<number | null>(null)
let generation = 0

const canManage = computed(() => serverAdmin.value && current.value?.can_manage === true)
const dirty = computed(() => current.value && draft.value && JSON.stringify(current.value.policy) !== JSON.stringify(draft.value))
const quotaTotal = computed(() => categories.reduce((sum, category) => sum + (draft.value?.category_quotas[quotaTask.value][category.key] ?? 0), 0))
const selectedVersion = computed(() => versions.value.find((item) => item.version === targetVersion.value))
const traceDetails = computed(() => {
  const value = trace.value
  if (!value) return []
  const result: { label: string; value: string | number }[] = []
  if (Number.isSafeInteger(value.policy_version)) result.push({ label: '使用策略版本', value: `v${value.policy_version}` })
  if (typeof value.task === 'string' && tasks.some((task) => task.key === value.task)) result.push({ label: '任务', value: taskLabel(value.task as BudgetTask) })
  const metrics: { keys: string[]; label: string }[] = [
    { keys: ['input_tokens', 'final_input_tokens', 'total_input_tokens'], label: '输入计数（Token）' },
    { keys: ['usable_input_limit', 'input_token_limit'], label: '可用输入上限（Token）' },
    { keys: ['cumulative_tokens', 'cumulative_input_tokens'], label: '累计处理量（Token）' },
    { keys: ['estimated_tokens'], label: '估算用量（Token）' },
  ]
  for (const metric of metrics) {
    const amount = metric.keys.map((key) => value[key]).find((number) => typeof number === 'number' && Number.isFinite(number))
    if (typeof amount === 'number') result.push({ label: metric.label, value: amount })
  }
  if (Array.isArray(value.calls)) result.push({ label: '预算记录中的调用数', value: value.calls.length })
  if (typeof value.count_method === 'string') result.push({ label: '计数口径', value: /conservative|estimate|byte|envelope/i.test(value.count_method) ? '保守估算' : '后端计数' })
  if (Array.isArray(value.omitted_ids) && value.omitted_ids.length) result.push({ label: '未完整处理条目数', value: value.omitted_ids.length })
  return result
})
const omissions = computed(() => {
  const counts = new Map<string, number>()
  if (trace.value?.reasons && typeof trace.value.reasons === 'object') {
    for (const [key, count] of Object.entries(trace.value.reasons)) {
      if (Number.isSafeInteger(count) && count > 0) counts.set(key, count)
    }
  } else if (Array.isArray(trace.value?.items)) {
    for (const item of trace.value.items) {
      if (item && item.selected === false && typeof item.reason === 'string') counts.set(item.reason, (counts.get(item.reason) || 0) + 1)
    }
  }
  return Array.from(counts, ([reason, count]) => ({ reason, count }))
})

function taskLabel(task: BudgetTask) { return tasks.find((item) => item.key === task)?.label || '默认任务' }
function fieldMin(field: BudgetField) {
  const bounds = current.value?.limits.parameter_bounds?.[field.key]
  if (bounds) return bounds[0]
  if (field.key === 'context_window') return current.value?.limits.context_min ?? field.min
  if (field.key === 'reserved_output') return current.value?.limits.output_min ?? field.min
  return field.min
}
function fieldMax(field: BudgetField) {
  const bounds = current.value?.limits.parameter_bounds?.[field.key]
  if (bounds) return bounds[1]
  if (field.key === 'context_window') return current.value?.limits.context_max
  if (field.key === 'reserved_output') return current.value?.limits.output_max
  if (field.key === 'max_stage_batches') return current.value?.limits.max_stage_batches
  if (field.key === 'summary_trigger_tokens') return current.value?.limits.context_max
  if (field.key === 'max_stage_tokens' && current.value) return current.value.limits.context_max * current.value.limits.max_stage_batches
  return field.max
}
function reasonLabel(reason: string) {
  const labels: Record<string, string> = {
    scope_denied: '无当前作用域权限', inactive: '记录已失效', superseded: '记录已被替代',
    source_retracted: '来源已撤回', summary_stale: '摘要需更新', duplicate: '重复内容',
    irrelevant: '与当前任务无关', low_priority: '优先级较低', budget_exceeded: '超过总预算',
    category_quota_pressure: '类别配额压力', covered_by_summary: '已由摘要覆盖',
    store_unavailable: '记忆服务暂不可用', semantic_unavailable: '语义检索暂不可用',
    tokenizer_unavailable: '采用保守计数', protected_overflow: '必要证据超出单次预算',
  }
  return labels[reason] || '其他省略或过滤原因'
}
function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未记录' : date.toLocaleString('zh-CN', { hour12: false })
}
function errorMessage(cause: unknown, fallback: string) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}
function clearData() {
  current.value = null; draft.value = null; versions.value = []; trace.value = null
  serverAdmin.value = false; targetVersion.value = null; conflict.value = false
}
function clonePolicy(policy: BudgetPolicy): BudgetPolicy {
  // Vue's nested proxies cannot be passed to structuredClone.
  return JSON.parse(JSON.stringify(policy)) as BudgetPolicy
}
function resetDraft() {
  if (current.value) draft.value = clonePolicy(current.value.policy)
  reason.value = ''; error.value = ''; notice.value = ''
}

async function load(): Promise<number | null> {
  if (!props.active) return null
  const requestId = ++generation
  const threadId = props.threadId
  clearData()
  loading.value = true; error.value = ''; traceError.value = ''; notice.value = ''
  const [identity, usage] = await Promise.allSettled([
    getCurrentDoctor(), threadId ? getBudgetTrace(threadId) : Promise.resolve(null),
  ])
  if (requestId !== generation || !props.active) return null
  if (usage.status === 'fulfilled') trace.value = usage.value?.data.trace ?? null
  else traceError.value = errorMessage(usage.reason, '预算记录读取失败，请刷新重试。')
  if (identity.status === 'fulfilled') serverAdmin.value = identity.value.data.capabilities?.budget_admin === true
  else error.value = errorMessage(identity.reason, '无法确认预算管理权限，请重新登录或刷新。')
  if (serverAdmin.value) {
    const [policy, history] = await Promise.allSettled([getBudgetPolicy(), getBudgetPolicyHistory()])
    if (requestId !== generation || !props.active) return null
    if (policy.status === 'fulfilled') {
      current.value = policy.value.data
      if (current.value.can_manage) {
        draft.value = clonePolicy(current.value.policy)
        if (history.status === 'fulfilled') versions.value = [...history.value.data.versions].sort((a, b) => b.version - a.version)
        else error.value = errorMessage(history.reason, '策略已读取，变更历史读取失败。')
      } else serverAdmin.value = false
    } else error.value = errorMessage(policy.reason, '预算策略读取失败，暂不能编辑。')
  }
  loading.value = false
  return requestId
}

function validatePolicy(policy: BudgetPolicy) {
  for (const field of fields) {
    const value = policy[field.key]
    const maximum = fieldMax(field)
    if (!Number.isSafeInteger(value) || value < fieldMin(field) || (maximum !== undefined && value > maximum)) return `请检查“${field.label}”的整数范围。`
  }
  if (policy.context_window - policy.reserved_output - policy.safety_margin < 2048) return '扣除输出预留与安全余量后，至少需要保留 2048 Token 的可用输入。'
  if (policy.summary_tokens + policy.minimal_background_tokens > policy.context_window - policy.reserved_output - policy.safety_margin) return '极简背景与详细摘要预算之和不能超过可用输入。'
  for (const task of tasks) {
    const weights = categories.map((category) => policy.category_quotas[task.key][category.key])
    if (weights.some((value) => !Number.isSafeInteger(value) || value < 0 || value > 100) || weights.reduce((sum, value) => sum + value, 0) !== 100) return `${task.label}的四项权重必须为 0–100 的整数且合计为 100。`
  }
  return ''
}

async function mutate(action: 'save' | 'rollback') {
  if (!canManage.value || !current.value || !draft.value || loading.value || busy.value || conflict.value) return
  error.value = ''; notice.value = ''
  if (!reason.value.trim()) { error.value = '请填写变更原因，便于审计和回退。'; return }
  if (action === 'save') {
    const problem = validatePolicy(draft.value)
    if (problem) { error.value = problem; return }
  } else if (targetVersion.value === null || targetVersion.value === current.value.version) return
  const requestId = generation
  const version = current.value.version
  const policy = clonePolicy(draft.value)
  const target = targetVersion.value
  const changeReason = reason.value.trim()
  busy.value = true
  try {
    if (action === 'save') await saveBudgetPolicy(version, policy, changeReason)
    else await rollbackBudgetPolicy(version, target!, changeReason)
    if (requestId !== generation || !props.active) return
    busy.value = false
    reason.value = ''
    const refreshed = await load()
    if (refreshed !== generation || !props.active) return
    notice.value = current.value ? `策略${action === 'save' ? '调整' : '回退'}已提交，当前生效版本 v${current.value.version}。` : '策略变更已提交，生效版本暂未读取到，请刷新确认。'
  } catch (cause) {
    if (requestId !== generation || !props.active) return
    const status = (cause as { response?: { status?: number } })?.response?.status
    if (status === 403) { serverAdmin.value = false; current.value = null; draft.value = null; versions.value = [] }
    if (status === 409) conflict.value = true
    error.value = status === 409 ? '策略已被其他管理员更新。请刷新生效版本后重新编辑。' : errorMessage(cause, '策略变更失败，不能视为已保存。')
  } finally { if (requestId === generation) busy.value = false }
}
function save() { return mutate('save') }
function rollback() { return mutate('rollback') }

watch(() => [props.active, props.threadId], () => {
  generation += 1
  clearData()
  loading.value = false; busy.value = false; error.value = ''; traceError.value = ''; notice.value = ''; reason.value = ''
  if (props.active) void load()
}, { immediate: true })
onBeforeUnmount(() => { generation += 1 })
</script>

<style scoped>
.budget-panel { display: grid; gap: 14px; color: #243746; }
.panel-heading { display: flex; align-items: flex-start; gap: 12px; }
.panel-heading p { flex: 1; margin: 0; font-size: 13px; line-height: 1.7; }
.muted { margin: 0; color: #657787; font-size: 12px; line-height: 1.7; }
.policy-status { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; }
.parameter-grid, .quota-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 18px; }
.parameter-grid :deep(.el-form-item__content), .quota-grid :deep(.el-form-item__content) { display: grid; gap: 5px; }
.parameter-grid :deep(.el-input-number), .quota-grid :deep(.el-input-number) { width: 100%; }
.parameter-grid small { color: #657787; line-height: 1.5; }
.quota-heading, .actions, .rollback-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.quota-heading { justify-content: space-between; margin-bottom: 8px; }
.task-select { width: 160px; }
.quota-grid { margin-top: 12px; }
.quota-total { margin: 0 0 14px; }
.invalid { color: #b34233; font-size: 12px; }
.actions { justify-content: flex-end; }
.version-history, .trace-panel { display: grid; gap: 12px; padding-top: 16px; border-top: 1px solid #e7edf1; }
.version-select { min-width: 190px; flex: 1; }
.version-list { font-size: 12px; }
.version-list summary { cursor: pointer; color: #35627d; }
.version-entry { display: grid; gap: 4px; padding: 12px 0; border-bottom: 1px solid #e7edf1; overflow-wrap: anywhere; }
.version-entry span { color: #657787; }
.version-entry p { margin: 0; white-space: pre-wrap; }
.trace-details { display: grid; gap: 8px; margin: 0; font-size: 12px; }
.trace-details div { display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: 10px; }
.trace-details dt { color: #657787; }
.trace-details dd { margin: 0; overflow-wrap: anywhere; }
.reason-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.reason-table caption { text-align: left; margin-bottom: 8px; color: #657787; }
.reason-table th, .reason-table td { text-align: left; padding: 8px; border-bottom: 1px solid #e7edf1; }
.reason-table th:last-child, .reason-table td:last-child { text-align: right; width: 70px; }
@media (max-width: 520px) {
  .panel-heading { flex-direction: column; }
  .parameter-grid, .quota-grid { grid-template-columns: minmax(0, 1fr); }
  .actions { justify-content: flex-start; }
  .trace-details div { grid-template-columns: 120px minmax(0, 1fr); }
}
</style>
