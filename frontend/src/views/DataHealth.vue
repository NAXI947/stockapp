<template>
  <div>
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">数据详情</h1>
        <p class="text-sm text-gray-500 mt-1">检查各数据表、字段最近业务日期和完成率</p>
      </div>
      <button
        @click="loadHealth"
        :disabled="loading"
        class="text-sm px-3 py-1.5 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:bg-gray-100 transition-colors"
      >
        {{ loading ? '检查中...' : '刷新' }}
      </button>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">监控表</p>
        <p class="text-2xl font-bold text-gray-900">{{ summary.table_count || 0 }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">正常</p>
        <p class="text-2xl font-bold text-green-600">{{ summary.ok_count || 0 }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">需关注</p>
        <p class="text-2xl font-bold text-yellow-600">{{ summary.warning_count || 0 }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">空表</p>
        <p class="text-2xl font-bold text-red-600">{{ summary.empty_count || 0 }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">最新交易日</p>
        <p class="text-xl font-bold text-gray-900">{{ formatDate(summary.market_latest_trade_date) }}</p>
      </div>
    </div>

    <div v-if="warnings.length" class="mb-6 bg-yellow-50 border border-yellow-100 rounded-lg p-4">
      <h2 class="text-sm font-medium text-yellow-800 mb-2">风险提示</h2>
      <div class="space-y-1">
        <p v-for="warning in warnings" :key="warning" class="text-sm text-yellow-700">{{ warning }}</p>
      </div>
    </div>

    <div v-if="error" class="bg-red-50 border border-red-100 text-red-700 rounded-lg p-4 text-sm">
      {{ error }}
    </div>

    <div v-else class="space-y-4">
      <div
        v-for="table in items"
        :key="table.table_name"
        class="bg-white rounded-lg shadow overflow-hidden"
      >
        <button
          @click="toggleTable(table.table_name)"
          class="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div class="flex items-center space-x-3 text-left">
            <span class="inline-flex w-16 justify-center px-2 py-1 text-xs rounded" :class="statusClass(table.status)">
              {{ statusText(table.status) }}
            </span>
            <div>
              <div class="font-medium text-gray-900">{{ table.label }}</div>
              <div class="text-xs text-gray-500">{{ table.table_name }}</div>
            </div>
          </div>
          <div class="hidden md:flex items-center space-x-8 text-right text-sm">
            <div>
              <div class="text-gray-500 text-xs">最新日期</div>
              <div class="text-gray-900">{{ formatDate(table.latest_date) }}</div>
            </div>
            <div>
              <div class="text-gray-500 text-xs">完成率</div>
              <div class="text-gray-900">{{ formatPercent(table.completion_rate) }}</div>
            </div>
            <div>
              <div class="text-gray-500 text-xs">行数</div>
              <div class="text-gray-900">{{ table.total_rows }}</div>
            </div>
          </div>
        </button>

        <div class="px-4 pb-4 border-t border-gray-100">
          <div class="grid grid-cols-2 md:grid-cols-5 gap-4 py-4 text-sm">
            <div>
              <div class="text-xs text-gray-500">最新日期字段</div>
              <div class="text-gray-900">{{ table.latest_date_field || '-' }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">最新日期行数</div>
              <div class="text-gray-900">{{ table.latest_rows }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">覆盖情况</div>
              <div class="text-gray-900">{{ table.completion_text }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">最近任务</div>
              <div class="text-gray-900">{{ table.latest_job_at || '-' }}</div>
            </div>
            <div class="col-span-2 md:col-span-1">
              <div class="text-xs text-gray-500">更新说明</div>
              <div class="text-gray-900" :title="table.updater">{{ table.updater || '-' }}</div>
            </div>
          </div>

          <div v-if="expandedTables.has(table.table_name)" class="overflow-x-auto">
            <table class="min-w-full">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">字段</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">最近有值日期</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">非空/基数</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">完成率</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">更新脚本</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                <tr v-for="field in table.fields" :key="`${table.table_name}-${field.field}`">
                  <td class="px-3 py-2 text-sm font-mono text-gray-700">{{ field.field }}</td>
                  <td class="px-3 py-2 text-sm text-gray-600">{{ formatDate(field.latest_date) }}</td>
                  <td class="px-3 py-2 text-sm text-gray-600">{{ field.non_null_rows }}/{{ field.total_rows }}</td>
                  <td class="px-3 py-2">
                    <span class="inline-flex px-2 py-1 text-xs rounded" :class="fieldStatusClass(field)">
                      {{ formatPercent(field.completion_rate) }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-sm text-gray-600 max-w-[360px]" :title="field.updater">
                    {{ field.updater || '-' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { dataApi } from '@/api'

const loading = ref(false)
const error = ref('')
const summary = ref({})
const items = ref([])
const warnings = ref([])
const expandedTables = ref(new Set())

async function loadHealth() {
  loading.value = true
  error.value = ''
  try {
    const data = await dataApi.getHealth()
    summary.value = data.summary || {}
    items.value = data.items || []
    warnings.value = data.warnings || []
    expandedTables.value = new Set(items.value.filter((item) => item.status !== 'ok').map((item) => item.table_name))
  } catch (err) {
    error.value = err.message || '数据检查失败'
  } finally {
    loading.value = false
  }
}

function toggleTable(tableName) {
  const next = new Set(expandedTables.value)
  if (next.has(tableName)) next.delete(tableName)
  else next.add(tableName)
  expandedTables.value = next
}

function statusText(status) {
  return { ok: '正常', warning: '关注', empty: '空表' }[status] || status
}

function statusClass(status) {
  if (status === 'ok') return 'bg-green-100 text-green-700'
  if (status === 'empty') return 'bg-red-100 text-red-700'
  return 'bg-yellow-100 text-yellow-700'
}

function fieldStatusClass(field) {
  if (field.status === 'ok') return 'bg-green-100 text-green-700'
  return 'bg-yellow-100 text-yellow-700'
}

function formatPercent(value) {
  if (value === null || value === undefined) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatDate(value) {
  if (!value) return '-'
  const text = String(value)
  if (/^\d{8}$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`
  }
  return text
}

onMounted(() => {
  loadHealth()
})
</script>
