<template>
  <div>
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">数据更新</h1>
        <p class="text-sm text-gray-500 mt-1">手动触发日更、周期更新、按日期补更并查看运行状态</p>
      </div>
      <div class="flex items-center space-x-2">
        <button
          @click="openTokenModal"
          class="text-sm px-3 py-1.5 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
        >
          Tushare 密钥
        </button>
        <button
          @click="loadTasks"
          class="text-sm px-3 py-1.5 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
        >
          刷新
        </button>
      </div>
    </div>

    <div class="mb-6 bg-white rounded-lg shadow p-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <button
          v-for="job in visibleJobs"
          :key="job.name"
          @click="startJob(job.name)"
          :disabled="runningJobs.has(job.name)"
          class="px-4 py-3 text-left border border-gray-200 rounded bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          <div class="text-sm font-medium text-gray-900">{{ job.label }}</div>
          <div class="text-xs text-gray-500 mt-1">{{ runningJobs.has(job.name) ? '运行中' : jobDescriptions[job.name] }}</div>
        </button>
      </div>
      <p v-if="feedback" class="mt-3 text-sm" :class="feedbackType === 'error' ? 'text-red-600' : 'text-green-600'">
        {{ feedback }}
      </p>
    </div>

    <div class="mb-6 bg-white rounded-lg shadow p-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label class="block flex-1">
          <span class="text-sm font-medium text-gray-700">按日期补更</span>
          <input
            v-model.trim="tradeDateInput"
            type="text"
            inputmode="numeric"
            maxlength="8"
            placeholder="YYYYMMDD"
            class="mt-1 w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </label>
        <button
          @click="startDateJob"
          :disabled="dateJobRunning || !isTradeDateInputValid"
          class="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          {{ dateJobRunning ? '运行中' : '更新该日期' }}
        </button>
      </div>
      <p v-if="dateFeedback" class="mt-3 text-sm" :class="dateFeedbackType === 'error' ? 'text-red-600' : 'text-green-600'">
        {{ dateFeedback }}
      </p>
    </div>

    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <h2 class="text-sm font-medium text-gray-700">运行记录（最近 6 条）</h2>
        <span class="text-xs text-gray-400" v-if="lastLoaded">更新于 {{ formatTime(lastLoaded) }}</span>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">任务</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">状态</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">进度</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">开始时间</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">结束时间</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">日志</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr v-if="!tasks.length">
              <td colspan="6" class="px-4 py-8 text-sm text-gray-400 text-center">暂无运行记录</td>
            </tr>
            <tr v-for="task in tasks" :key="task.task_id">
              <td class="px-4 py-3">
                <div class="text-sm font-medium text-gray-900">{{ task.label }}</div>
                <div class="text-xs text-gray-500">{{ task.job_name }}</div>
              </td>
              <td class="px-4 py-3">
                <span class="inline-flex px-2 py-1 text-xs rounded" :class="statusClass(task.status)">
                  {{ statusText(task.status) }}
                </span>
                <div v-if="task.message" class="text-xs text-gray-500 mt-1">{{ task.message }}</div>
              </td>
              <td class="px-4 py-3 min-w-[260px]">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-xs font-medium text-gray-700 truncate">{{ progressCurrent(task) }}</span>
                  <span class="text-xs text-gray-400 shrink-0">{{ progressPercentText(task) }}</span>
                </div>
                <div class="mt-2 h-2 w-full rounded bg-gray-100 overflow-hidden">
                  <div
                    class="h-full rounded transition-all duration-300"
                    :class="progressBarClass(task)"
                    :style="{ width: `${progressPercent(task)}%` }"
                  ></div>
                </div>
                <div class="text-xs text-gray-500 mt-1 truncate" :title="progressDetail(task)">
                  {{ progressDetail(task) }}
                </div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ task.started_at || '-' }}</td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ task.finished_at || '-' }}</td>
              <td class="px-4 py-3 text-xs text-gray-500 max-w-[360px] truncate" :title="task.log_file">
                {{ task.log_file || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showTokenModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div class="w-full max-w-md bg-white rounded-lg shadow-lg">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 class="text-base font-semibold text-gray-900">Tushare 密钥</h2>
          <button class="text-gray-400 hover:text-gray-600" @click="closeTokenModal">×</button>
        </div>
        <div class="px-5 py-4 space-y-4">
          <div class="text-sm text-gray-600">
            当前状态：
            <span :class="tokenStatus.configured ? 'text-green-600' : 'text-red-600'">
              {{ tokenStatus.configured ? tokenStatus.masked_token : '未配置' }}
            </span>
          </div>
          <label class="block">
            <span class="text-sm text-gray-700">新密钥</span>
            <input
              v-model.trim="tokenInput"
              type="password"
              autocomplete="off"
              class="mt-1 w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="输入 Tushare token"
            />
          </label>
          <p v-if="tokenFeedback" class="text-sm" :class="tokenFeedbackType === 'error' ? 'text-red-600' : 'text-green-600'">
            {{ tokenFeedback }}
          </p>
          <p class="text-xs text-gray-400 truncate" :title="tokenStatus.config_path">
            保存位置：{{ tokenStatus.config_path || '-' }}
          </p>
        </div>
        <div class="px-5 py-4 border-t border-gray-100 flex justify-end space-x-2">
          <button
            @click="closeTokenModal"
            class="text-sm px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            @click="saveToken"
            :disabled="savingToken || !tokenInput"
            class="text-sm px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {{ savingToken ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { configApi, jobApi } from '@/api'

const jobs = ref([])
const tasks = ref([])
const feedback = ref('')
const feedbackType = ref('success')
const lastLoaded = ref(null)
const showTokenModal = ref(false)
const tokenInput = ref('')
const tokenStatus = ref({ configured: false, masked_token: '', config_path: '' })
const tokenFeedback = ref('')
const tokenFeedbackType = ref('success')
const savingToken = ref(false)
const tradeDateInput = ref('')
const dateFeedback = ref('')
const dateFeedbackType = ref('success')
let timer = null

const preferredOrder = ['daily', 'weekly', 'monthly', 'yearly']
const jobDescriptions = {
  daily: '最新交易日行情、龙虎榜、筹码、策略字段',
  weekly: '申万行业与股票基础扩展字段',
  monthly: '概念明细、限售解禁、受影响策略局部重算',
  yearly: '财务指标与策略全量重算'
}

const visibleJobs = computed(() => {
  const byName = new Map(jobs.value.map((job) => [job.name, job]))
  const ordered = preferredOrder.map((name) => byName.get(name)).filter(Boolean)
  const orderedNames = new Set(ordered.map((job) => job.name))
  const extras = jobs.value.filter((job) => !orderedNames.has(job.name) && job.name !== 'update_date')
  return [...ordered, ...extras]
})

const runningJobs = computed(() => new Set(
  tasks.value.filter((task) => task.status === 'running').map((task) => task.job_name)
))

const dateJobRunning = computed(() => runningJobs.value.has('update_date'))
const isTradeDateInputValid = computed(() => /^\d{8}$/.test(tradeDateInput.value))

async function loadDefinitions() {
  const data = await jobApi.getDefinitions()
  jobs.value = data.items || []
}

async function loadTasks() {
  const data = await jobApi.getTasks()
  tasks.value = data.items || []
  lastLoaded.value = new Date()
}

async function startJob(jobName) {
  feedback.value = ''
  try {
    const data = await jobApi.runJob(jobName)
    feedbackType.value = 'success'
    feedback.value = `${data.task.label} 已开始`
    await loadTasks()
    ensurePolling()
  } catch (error) {
    feedbackType.value = 'error'
    feedback.value = error.message || '启动失败'
  }
}

async function startDateJob() {
  dateFeedback.value = ''
  if (!isTradeDateInputValid.value) {
    dateFeedbackType.value = 'error'
    dateFeedback.value = '请输入 8 位日期，例如 20260527'
    return
  }
  try {
    const data = await jobApi.runDailyDate(tradeDateInput.value)
    dateFeedbackType.value = 'success'
    dateFeedback.value = `${data.task.label} 已开始`
    await loadTasks()
    ensurePolling()
  } catch (error) {
    dateFeedbackType.value = 'error'
    dateFeedback.value = error.message || '启动失败'
  }
}

async function openTokenModal() {
  showTokenModal.value = true
  tokenInput.value = ''
  tokenFeedback.value = ''
  await loadTokenStatus()
}

function closeTokenModal() {
  showTokenModal.value = false
}

async function loadTokenStatus() {
  tokenStatus.value = await configApi.getTushareToken()
}

async function saveToken() {
  tokenFeedback.value = ''
  savingToken.value = true
  try {
    tokenStatus.value = await configApi.updateTushareToken(tokenInput.value)
    tokenFeedbackType.value = 'success'
    tokenFeedback.value = '密钥已保存，后续更新任务会使用新密钥'
    tokenInput.value = ''
  } catch (error) {
    tokenFeedbackType.value = 'error'
    tokenFeedback.value = error.message || '保存失败'
  } finally {
    savingToken.value = false
  }
}

function ensurePolling() {
  if (timer) return
  timer = window.setInterval(async () => {
    await loadTasks()
    if (!tasks.value.some((task) => task.status === 'running')) {
      clearPolling()
    }
  }, 3000)
}

function clearPolling() {
  if (timer) {
    window.clearInterval(timer)
    timer = null
  }
}

function statusText(status) {
  return { running: '运行中', success: '成功', failed: '失败' }[status] || status
}

function statusClass(status) {
  if (status === 'success') return 'bg-green-100 text-green-700'
  if (status === 'failed') return 'bg-red-100 text-red-700'
  return 'bg-blue-100 text-blue-700'
}

function progressPercent(task) {
  const value = task?.progress?.percent
  if (Number.isFinite(value)) return Math.min(Math.max(Math.round(value), 0), 100)
  if (task.status === 'success') return 100
  return task.status === 'running' ? 8 : 0
}

function progressPercentText(task) {
  const value = task?.progress?.percent
  if (Number.isFinite(value)) return `${progressPercent(task)}%`
  if (task.status === 'running') return '进行中'
  return task.status === 'success' ? '100%' : '-'
}

function progressCurrent(task) {
  return task?.progress?.current || (task.status === 'running' ? '等待日志更新' : '-')
}

function progressDetail(task) {
  return task?.progress?.detail || (task.status === 'running' ? '任务已启动，正在收集进度' : '-')
}

function progressBarClass(task) {
  if (task.status === 'failed') return 'bg-red-500'
  if (task.status === 'success') return 'bg-green-500'
  return 'bg-blue-500'
}

function formatTime(date) {
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

onMounted(async () => {
  await Promise.all([loadDefinitions(), loadTasks(), loadTokenStatus()])
  if (tasks.value.some((task) => task.status === 'running')) ensurePolling()
})

onUnmounted(() => {
  clearPolling()
})
</script>
