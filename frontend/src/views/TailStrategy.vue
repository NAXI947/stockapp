<template>
  <div>
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">尾盘策略选股</h1>
        <p class="text-sm text-gray-500 mt-1">
          共 {{ store.count }} 只股票
          <span v-if="lastUpdate" class="text-xs text-gray-400 ml-2">
            更新于 {{ formatTime(lastUpdate) }}
          </span>
        </p>
      </div>
      <!-- 导出按钮 -->
      <div class="flex items-center space-x-2">
        <label
          class="text-xs px-3 py-1.5 bg-yellow-500 text-white rounded hover:bg-yellow-600 transition-colors flex items-center space-x-1 cursor-pointer"
        >
          <span>📁</span>
          <span>上传Excel</span>
          <input type="file" class="hidden" accept=".xlsx, .xls" @change="handleFileUpload" />
        </label>
        <button
          v-if="store.count > 0"
          @click="exportJSON"
          class="text-xs px-3 py-1.5 bg-green-500 text-white rounded hover:bg-green-600 transition-colors flex items-center space-x-1"
        >
          <span>📥</span>
          <span>JSON</span>
        </button>
        <button
          v-if="store.count > 0"
          @click="exportCSV"
          class="text-xs px-3 py-1.5 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors flex items-center space-x-1"
        >
          <span>📊</span>
          <span>CSV</span>
        </button>
      </div>
    </div>
    
    <!-- 批量添加自选股 -->
    <div class="mb-6 bg-white rounded-lg shadow p-4">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-medium text-gray-700">批量添加自选股</h2>
      </div>
      <div class="flex flex-col space-y-2">
        <textarea
          v-model="batchInput"
          placeholder="请输入股票代码或名称，每行一个或用空格、逗号分隔&#10;代码示例：600643、002950&#10;名称示例：爱建集团、奥美医疗"
          class="w-full text-sm px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px]"
        ></textarea>
        <div class="flex items-center justify-between">
          <span class="text-xs" :class="batchFeedback.includes('失败') ? 'text-red-500' : 'text-gray-500'">
            {{ batchFeedback || '支持一次性匹配多个股票代码或名称' }}
          </span>
          <button
            @click="handleBatchAdd"
            :disabled="isBatchAdding || !batchInput.trim()"
            class="text-sm px-4 py-1.5 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {{ isBatchAdding ? '匹配中...' : '批量添加' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- 加载中 -->
    <Loading v-if="loading && !stocks.length" />
    
    <!-- 空状态 -->
    <Empty
      v-else-if="!store.count"
      icon="⭐"
      title="暂无股票"
      description="在选股页面点击星标添加或上传Excel文件"
    />
    
    <!-- 列表 -->
    <div v-else class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票</th>
              <th 
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                @click="sortBy('final_score')"
              >
                <div class="flex items-center space-x-1">
                  <span>{{ getStrategyFieldLabel('final_score') }}</span>
                  <span v-if="sortKey === 'final_score'" class="text-blue-500">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th 
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                @click="sortBy('pct_chg')"
              >
                <div class="flex items-center space-x-1">
                  <span>{{ getStrategyFieldLabel('pct_chg') }}</span>
                  <span v-if="sortKey === 'pct_chg'" class="text-blue-500">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ getStrategyFieldLabel('turnover_rate') }}</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ getStrategyFieldLabel('chip_vacuum') }}</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ getStrategyFieldLabel('safety_margin') }}</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ getStrategyFieldLabel('trend_baseline') }}</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">风险</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr
              v-for="item in sortedStocks"
              :key="item.tsCode"
              class="hover:bg-gray-50 cursor-pointer"
              @click="goToDetail(item.tsCode)"
            >
              <td class="px-4 py-3">
                <div class="text-sm font-medium text-gray-900">{{ item.name }}</div>
                <div class="text-xs text-gray-500">{{ item.tsCode }}</div>
                <div class="mt-2 flex flex-wrap gap-1.5">
                  <span
                    v-if="item.industry"
                    class="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
                  >
                    {{ item.industry }}
                  </span>
                  <span
                    v-for="concept in getVisibleConcepts(item)"
                    :key="`${item.tsCode}-${concept}`"
                    class="text-xs bg-sky-100 text-sky-700 px-2 py-0.5 rounded"
                    :title="getConceptText(item) || concept"
                  >
                    {{ concept }}
                  </span>
                  <span
                    v-if="getConceptOverflow(item) > 0"
                    class="text-xs bg-sky-50 text-sky-600 px-2 py-0.5 rounded"
                    :title="getConceptText(item) || ''"
                  >
                    +{{ getConceptOverflow(item) }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-3">
                <span 
                  v-if="item.data"
                  class="text-sm font-mono font-bold"
                  :class="getScoreClass(item.data.final_score)"
                >
                  {{ item.data.final_score }}
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3">
                <span 
                  class="text-sm font-mono"
                  :class="getPctChg(item) >= 0 ? 'text-up' : 'text-down'"
                >
                  {{ formatPercent(getPctChg(item)) }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span class="text-sm text-gray-600">
                  {{ formatNumber(getTurnoverRate(item)) }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span class="text-sm font-mono text-gray-600">
                  {{ item.data ? formatFlag(item.data.chip_vacuum) : '-' }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span class="text-sm font-mono text-gray-600">
                  {{ item.data ? formatFlag(item.data.safety_margin) : '-' }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span class="text-sm font-mono text-gray-600">
                  {{ item.data ? formatFlag(item.data.trend_baseline) : '-' }}
                </span>
              </td>
              <td class="px-4 py-3">
                <div v-if="item.data" class="space-y-1">
                  <span 
                    v-if="item.data.float_risk_7d" 
                    class="inline-block px-2 py-0.5 text-xs bg-red-100 text-red-700 rounded"
                  >
                    解禁风险
                  </span>
                  <span 
                    v-if="item.data.limit_up_20d > 0" 
                    class="inline-block px-2 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded"
                  >
                    近20日{{ item.data.limit_up_20d }}涨停
                  </span>
                  <span 
                    v-if="!item.data.float_risk_7d && !item.data.limit_up_20d" 
                    class="text-xs text-green-600"
                  >
                    ✅ 正常
                  </span>
                </div>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3">
                <div class="flex items-center space-x-2">
                  <button
                    @click.stop="openReview(item)"
                    class="text-blue-500 hover:text-blue-700 text-sm px-2 py-1 rounded hover:bg-blue-50"
                    title="记录复盘"
                  >
                    复盘
                  </button>
                  <button
                    @click.stop="store.remove(item.tsCode)"
                    class="text-red-500 hover:text-red-700 text-sm px-2 py-1 rounded hover:bg-red-50"
                  >
                    移除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- 刷新按钮 -->
      <div class="px-4 py-3 bg-gray-50 border-t flex justify-between items-center">
        <span class="text-sm text-gray-500">
          点击股票查看详情
        </span>
        <button
          @click="refreshData"
          :disabled="loading"
          class="text-sm px-3 py-1 bg-white border rounded hover:bg-gray-50 disabled:opacity-50 flex items-center space-x-1"
        >
          <span>{{ loading ? '刷新中...' : '刷新数据' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTailStrategyStore } from '@/stores/tailStrategy'
import { stockApi } from '@/api'
import Loading from '@/components/Loading.vue'
import Empty from '@/components/Empty.vue'
import * as XLSX from 'xlsx'
import { getStrategyFieldLabel } from '@/constants/strategyFields'

const router = useRouter()
const store = useTailStrategyStore()

const loading = ref(false)
const error = ref('')
const errorType = ref('unknown')
const stocks = ref([])
const lastUpdate = ref(null)
const sortKey = ref('final_score')
const sortOrder = ref('desc')

const batchInput = ref('')
const isBatchAdding = ref(false)
const batchFeedback = ref('')

// 合并 store 和实时数据
const sortedStocks = computed(() => {
  const list = store.list.map(item => {
    const data = stocks.value.find(s => s.ts_code === item.tsCode)
    return {
      ...item,
      data: data || null
    }
  })
  
  // 排序
  list.sort((a, b) => {
    const va = a.data?.[sortKey.value] || a[sortKey.value]
    const vb = b.data?.[sortKey.value] || b[sortKey.value]
    
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    
    if (va < vb) return sortOrder.value === 'asc' ? -1 : 1
    if (va > vb) return sortOrder.value === 'asc' ? 1 : -1
    return 0
  })
  
  return list
})

function getPctChg(item) {
  if (item.data && item.data.pct_chg != null) return item.data.pct_chg
  return item.today_pct
}

function getTurnoverRate(item) {
  if (item.data && item.data.turnover_rate != null) return item.data.turnover_rate
  return item.turnover_rate_excel
}

function sortBy(key) {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'desc'
  }
}

function getScoreClass(score) {
  if (score >= 70) return 'text-green-600'
  if (score >= 50) return 'text-yellow-600'
  return 'text-gray-600'
}

function formatPercent(val) {
  if (val == null) return '-'
  const sign = val > 0 ? '+' : ''
  return `${sign}${Number(val).toFixed(2)}%`
}

function formatNumber(val) {
  if (val == null) return '-'
  return Number(val).toFixed(2)
}

function formatFlag(val) {
  if (val == null) return '-'
  return Number(val) === 1 ? '是' : '否'
}

function formatTime(date) {
  if (!date) return '-'
  const d = new Date(date)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function getConceptNames(item) {
  let concepts = item.data?.concept_names || item.conceptNames || []
  if (typeof concepts === 'string') concepts = concepts.split(/[,\s]+/)
  if (!Array.isArray(concepts)) concepts = []
  return concepts
}

function getConceptText(item) {
  return item.data?.concept_text || item.conceptText || getConceptNames(item).join(' / ')
}

function getVisibleConcepts(item) {
  return getConceptNames(item).slice(0, 4)
}

function getConceptOverflow(item) {
  return Math.max(getConceptNames(item).length - 4, 0)
}

function goToDetail(tsCode) {
  router.push(`/stock/${tsCode}`)
}

function openReview(stock) {
  router.push({
    path: '/review',
    query: {
      tsCode: stock.tsCode,
      name: stock.name
    }
  })
}

async function refreshData() {
  if (!store.count) return
  
  loading.value = true
  error.value = ''
  errorType.value = 'unknown'
  stocks.value = []
  
  try {
    const promises = store.list.map(async (item) => {
      try {
        const data = await stockApi.getDetail(item.tsCode)
        return data
      } catch (err) {
        return null
      }
    })
    
    const results = await Promise.all(promises)
    stocks.value = results.filter(Boolean)
    lastUpdate.value = new Date()
  } catch (err) {
    error.value = err.message
    errorType.value = err.type || 'unknown'
  } finally {
    loading.value = false
  }
}

watch(() => store.list, () => {
  refreshData()
}, { deep: true })

// ========== 批量添加 ==========

async function handleBatchAdd() {
  if (!batchInput.value.trim()) return
  
  const queries = batchInput.value
    .split(/[\n\s,，]+/)
    .map(q => q.trim())
    .filter(Boolean)
    
  if (!queries.length) return
  
  isBatchAdding.value = true
  batchFeedback.value = '正在查找股票...'
  
  try {
    const res = await stockApi.batchSearch(queries)
    const items = res?.items || []
    
    let addedCount = 0
    let existCount = 0
    
    for (const item of items) {
      if (store.isInWatchlist(item.ts_code)) {
        existCount++
      } else {
        store.add({
          tsCode: item.ts_code,
          name: item.name,
          industry: item.industry || '',
          conceptNames: item.concept_names || [],
          conceptText: item.concept_text || ''
        })
        addedCount++
      }
    }
    
    batchFeedback.value = `匹配到 ${items.length} 只股票：成功添加 ${addedCount} 只，已存在 ${existCount} 只`
    if (addedCount > 0) {
      batchInput.value = ''
      setTimeout(() => { batchFeedback.value = '' }, 3000)
    } else if (items.length === 0) {
      batchFeedback.value = '未找到匹配的股票，请检查输入是否正确'
    } else {
      setTimeout(() => { batchFeedback.value = '' }, 3000)
    }
  } catch (err) {
    batchFeedback.value = '搜索失败：' + (err.message || '未知错误')
  } finally {
    isBatchAdding.value = false
  }
}

// ========== 文件上传 ==========

function formatTsCode(codeObj) {
  let codeStr = String(codeObj).trim()
  // Add leading zeros if missing
  if (codeStr.length < 6 && /^\d+$/.test(codeStr)) {
    codeStr = codeStr.padStart(6, '0')
  }
  if (codeStr.startsWith('6')) return `${codeStr}.SH`
  if (codeStr.startsWith('0') || codeStr.startsWith('3')) return `${codeStr}.SZ`
  if (codeStr.startsWith('8') || codeStr.startsWith('4')) return `${codeStr}.BJ`
  return `${codeStr}.SH` // default
}

function handleFileUpload(event) {
  const file = event.target.files[0]
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const data = new Uint8Array(e.target.result)
      const workbook = XLSX.read(data, { type: 'array' })
      const firstSheetName = workbook.SheetNames[0]
      const worksheet = workbook.Sheets[firstSheetName]
      const json = XLSX.utils.sheet_to_json(worksheet)
      
      const newStocks = []
      json.forEach(row => {
        let tsCode = ''
        let name = ''
        let today_pct = null
        let volume_ratio = null
        let turnover_rate = null
        let amplitude = null
        let main_net_inflow = null
        let realtime_winner_rate = null
        let realtime_top_list = null
        let conceptText = ''

        for (const key of Object.keys(row)) {
          const val = row[key]
          if (key.includes('代码')) tsCode = formatTsCode(val)
          else if (key.includes('名称')) name = val
          else if (key.includes('涨跌幅')) today_pct = parseFloat(val)
          else if (key.includes('量比')) volume_ratio = parseFloat(val)
          else if (key.includes('换手率')) turnover_rate = parseFloat(val)
          else if (key.includes('振幅')) amplitude = parseFloat(val)
          else if (key.includes('主力净额')) {
            // handle strings like "8500.5万"
            let num = String(val).replace(/[^0-9.-]/g, '')
            main_net_inflow = parseFloat(num)
          }
          else if (key.includes('获利盘')) realtime_winner_rate = parseFloat(val)
          else if (key.includes('龙虎榜')) realtime_top_list = val
          else if (key.includes('概念')) conceptText = val
        }
        
        if (tsCode) {
          newStocks.push({
            tsCode,
            name,
            today_pct,
            volume_ratio,
            turnover_rate,
            amplitude,
            main_net_inflow,
            realtime_winner_rate,
            realtime_top_list,
            conceptText,
            conceptNames: conceptText ? conceptText.split(/[,\s、]+/) : []
          })
        }
      })
      
      if (newStocks.length > 0) {
        store.addBatch(newStocks)
        alert(`成功从Excel中解析并添加(或更新)了 ${newStocks.length} 只股票`)
      } else {
        alert('未能从Excel中解析出有效的股票代码')
      }
    } catch (err) {
      console.error(err)
      alert('解析Excel文件失败')
    }
    event.target.value = ''
  }
  reader.readAsArrayBuffer(file)
}

// ========== 导出功能 ==========

function getExportFilename(ext) {
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  return `tailStrategy_${date}.${ext}`
}

function exportJSON() {
  if (!sortedStocks.value.length) return
  
  const formattedData = sortedStocks.value.map(item => {
    const d = item.data || {}
    let reject_reason = ''
    if (d.float_risk_7d) reject_reason += 'float_risk_7d,'
    if (d.final_score != null && d.final_score < 15) reject_reason += 'base_score<15'
    reject_reason = reject_reason.replace(/,$/, '')
    
    return {
      ts_code: item.tsCode,
      name: item.name,
      // ---- 数据来自上传的EXCEL里 ----
      today_pct: item.today_pct,
      volume_ratio: item.volume_ratio,
      turnover_rate: item.turnover_rate_excel,
      amplitude: item.amplitude,
      main_net_inflow: item.main_net_inflow,
      realtime_winner_rate: item.realtime_winner_rate,
      realtime_top_list: item.realtime_top_list,
      concept: item.conceptText,
      // ---- 数据来自本地数据库 ----
      local_final_score: d.final_score,
      chip_vacuum: d.chip_vacuum != null ? d.chip_vacuum : null,
      safety_margin: d.safety_margin != null ? d.safety_margin : null,
      final_score: d.final_score,
      rejected: reject_reason ? 1 : 0,
      reject_reason: reject_reason
    }
  })
  
  const blob = new Blob([JSON.stringify(formattedData, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = getExportFilename('json')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function exportCSV() {
  if (!sortedStocks.value.length) return
  
  const headers = [
    '股票代码', '股票名称', '行业', '概念股', '最新策略分', '涨跌幅(%)', '换手率(%)', '解禁风险', '近期涨停', '添加时间'
  ]
  
  const rows = sortedStocks.value.map(item => {
    const d = item.data || {}
    let risk = '无'
    if (d.float_risk_7d) risk = '是(7日内)'
    
    return [
      item.tsCode,
      item.name || '',
      item.industry || '',
      getConceptText(item) || '',
      d.final_score != null ? d.final_score : '-',
      getPctChg(item) != null ? getPctChg(item).toFixed(2) : '-',
      getTurnoverRate(item) != null ? getTurnoverRate(item).toFixed(2) : '-',
      risk,
      d.limit_up_20d > 0 ? `近20日${d.limit_up_20d}个` : '-',
      formatTime(item.addedAt) || ''
    ]
  })
  
  const escapeCSV = (val) => {
    const str = String(val)
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return '"' + str.replace(/"/g, '""') + '"'
    }
    return str
  }
  
  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.map(escapeCSV).join(','))
  ].join('\n')
  
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = getExportFilename('csv')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

onMounted(() => {
  refreshData()
})
</script>
