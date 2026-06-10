<template>
  <div>
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">策略选股 v1.2</h1>
        <p class="text-sm text-gray-500 mt-1">
          最新交易日：{{ tradeDate || '-' }}
          <span class="ml-2 text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
            {{ modeLabel }}
          </span>
          <span
            v-if="mode === 'normal'"
            class="ml-2 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded"
          >
            页面仅显示 95 分及以上，导出含全量
          </span>
          <span
            v-else
            class="ml-2 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded"
          >
            导出当前埋伏池数据
          </span>
        </p>
      </div>
      <!-- 导出按钮 -->
      <div v-if="picks.length" class="flex items-center space-x-2">
        <button
          @click="exportJSON"
          class="text-xs px-3 py-1.5 bg-green-500 text-white rounded hover:bg-green-600 transition-colors flex items-center space-x-1"
        >
          <span>📥</span>
          <span>JSON</span>
        </button>
        <button
          @click="exportCSV"
          class="text-xs px-3 py-1.5 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors flex items-center space-x-1"
        >
          <span>📊</span>
          <span>CSV</span>
        </button>
      </div>
    </div>
    
    <!-- 模式切换按钮 -->
    <div class="mb-4 flex items-center space-x-2">
      <button
        @click="switchMode('normal')"
        :class="mode === 'normal' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700'"
        class="px-4 py-2 rounded-lg transition-colors"
      >
        🔥 爆发右侧
      </button>
      <button
        @click="switchMode('ambush')"
        :class="mode === 'ambush' ? 'bg-emerald-500 text-white' : 'bg-gray-200 text-gray-700'"
        class="px-4 py-2 rounded-lg transition-colors"
      >
        🥷 预期埋伏
      </button>
    </div>
    
    <!-- 搜索框 -->
    <div class="mb-4 flex items-center space-x-2">
      <div class="flex-1 relative">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索股票代码或名称..."
          class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <span v-if="searchQuery" @click="searchQuery = ''" class="absolute right-3 top-2.5 text-gray-400 cursor-pointer hover:text-gray-600">
          ✕
        </span>
      </div>
      <span v-if="searchQuery" class="text-sm text-gray-500">
        找到 {{ filteredPicks.length }} 只
      </span>
    </div>
    
    <!-- 策略说明（爆发右侧模式） -->
    <div v-if="mode === 'normal'" class="mb-4 bg-blue-50 border border-blue-100 rounded-lg p-3 text-sm text-blue-800">
      <div class="flex items-center space-x-2 mb-2">
        <span class="font-medium">策略规则 v1.1：</span>
        <span class="text-xs bg-blue-100 px-2 py-0.5 rounded">6项准入条件 + 6项打分</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-xs">
        <div>✓ 收盘价 > ma60</div>
        <div>✓ 上方筹码 < 10%</div>
        <div>✓ K线实体 > 0.6</div>
        <div>✓ 量比 ≥ 1.8 且换手 ≥ 2%</div>
        <div>✓ 偏离ma20 < 25%</div>
        <div>✓ 非ST股</div>
      </div>
    </div>

    <!-- 策略说明（预期埋伏模式） -->
    <div v-else class="mb-4 bg-emerald-50 border border-emerald-100 rounded-lg p-3 text-sm text-emerald-800">
      <div class="flex items-center space-x-2 mb-2">
        <span class="font-medium">埋伏池规则 v1.2：</span>
        <span class="text-xs bg-emerald-100 px-2 py-0.5 rounded">手工池 + 动态异动跟踪</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-xs">
        <div>✓ 仅显示监控中股票</div>
        <div>✓ 保留埋伏预期逻辑</div>
        <div>✓ 跟踪筹码真空度</div>
        <div>✓ 跟踪安全边际</div>
        <div>✓ 跟踪量能活跃</div>
        <div>✓ 量能或K线达标标记异动</div>
      </div>
    </div>
    
    <!-- 加载中 -->
    <Loading v-if="loading" />
    
    <!-- 错误 -->
    <Error
      v-else-if="error"
      :type="errorType"
      :message="error"
      :details="errorDetails"
      @retry="fetchPicks"
    />
    
    <!-- 空数据（无搜索词时） -->
    <Empty
      v-else-if="!searchQuery && !picks.length"
      :icon="emptyState.icon"
      :title="emptyState.title"
      :description="emptyState.description"
    />

    <!-- 搜索结果为空 -->
    <Empty
      v-else-if="searchQuery && !filteredPicks.length"
      icon="🔎"
      title="没有匹配结果"
      description="请尝试股票代码、名称，或清空搜索条件"
    />

    <!-- 无搜索词时，筛选结果为空 -->
    <Empty
      v-else-if="!searchQuery && !filteredPicks.length"
      icon="🎯"
      title="暂无 95 分以上股票"
      description="当前交易日没有满足前端展示门槛的股票，导出仍可获取全量数据"
    />
    
    <!-- 数据表格 -->
    <div v-else class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full">
          <thead class="bg-gray-50">
            <tr>
              <th
                v-for="col in columns"
                :key="col.key"
                class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                @click="sortBy(col.key)"
              >
                <div class="flex items-center space-x-1">
                  <span>{{ col.title }}</span>
                  <span v-if="sortKey === col.key" class="text-blue-500">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th v-if="mode !== 'ambush'" class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                准入
              </th>
              <th class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                操作
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr
              v-for="stock in sortedPicks"
              :key="stock.ts_code"
              class="hover:bg-gray-50 cursor-pointer"
              :class="{
                'bg-amber-50 border-l-4 border-amber-400': stock.is_action_triggered,
                'bg-gray-50 opacity-60': stock.rejected
              }"
              @click="goToDetail(stock.ts_code)"
            >
              <!-- 股票名称列（两种模式通用） -->
              <td class="px-3 py-3 whitespace-nowrap">
                <div class="flex items-center space-x-2">
                  <span v-if="stock.is_action_triggered" class="text-amber-500">🔥</span>
                  <div>
                    <div class="text-sm font-medium text-gray-900">{{ stock.name }}</div>
                    <div class="text-xs text-gray-500">{{ stock.ts_code }}</div>
                  </div>
                </div>
              </td>
              <!-- 动态列（根据 columns 配置渲染） -->
              <td
                v-for="col in columns.slice(1)"
                :key="col.key"
                class="px-3 py-3 whitespace-nowrap"
              >
                <!-- 行业 -->
                <template v-if="col.key === 'industry'">
                  <span class="text-sm text-gray-600">{{ stock.industry || '-' }}</span>
                </template>
                <!-- 涨跌幅 -->
                <template v-else-if="col.key === 'pct_chg'">
                  <span
                    class="text-sm font-mono font-medium"
                    :class="stock.pct_chg >= 0 ? 'text-up' : 'text-down'"
                  >
                    {{ formatPercent(stock.pct_chg) }}
                  </span>
                </template>
                <!-- 换手率 -->
                <template v-else-if="col.key === 'turnover_rate'">
                  <span class="text-sm text-gray-600">{{ formatNumber(stock.turnover_rate) }}%</span>
                </template>
                <!-- 量比 -->
                <template v-else-if="col.key === 'volume_ratio'">
                  <span class="text-sm text-gray-600">{{ formatNumber(stock.volume_ratio) }}</span>
                </template>
                <!-- 胜率 -->
                <template v-else-if="col.key === 'winner_rate'">
                  <span class="text-sm text-gray-600">{{ formatNumber(stock.winner_rate) }}%</span>
                </template>
                <!-- 策略分 -->
                <template v-else-if="col.key === 'final_score'">
                  <span class="text-sm font-mono font-bold" :class="getScoreClass(stock.final_score)">
                    {{ stock.final_score }}
                  </span>
                </template>
                <!-- 标签 -->
                <template v-else-if="col.key === 'top_list_3d'">
                  <div class="flex items-center space-x-1">
                    <span
                      v-for="concept in getVisibleConcepts(stock)"
                      :key="`${stock.ts_code}-${concept}`"
                      class="text-xs bg-sky-100 text-sky-700 px-1.5 py-0.5 rounded"
                      :title="stock.concept_text || concept"
                    >
                      {{ concept }}
                    </span>
                    <span
                      v-if="getConceptOverflow(stock) > 0"
                      class="text-xs bg-sky-50 text-sky-600 px-1.5 py-0.5 rounded"
                      :title="stock.concept_text || ''"
                    >
                      +{{ getConceptOverflow(stock) }}
                    </span>
                    <span
                      v-if="stock.top_list_3d"
                      class="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded"
                      title="近3日龙虎榜"
                    >
                      龙虎
                    </span>
                    <span
                      v-if="stock.st_risk"
                      class="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded"
                    >
                      ST
                    </span>
                  </div>
                </template>
                <!-- 量能活跃（埋伏模式用文字映射，正常模式用勾叉） -->
                <template v-else-if="col.key === 'liquidity_base'">
                  <span
                    class="text-sm font-mono"
                    :class="stock.is_action_triggered ? 'text-amber-500 font-semibold' : 'text-gray-400'"
                  >
                    {{ stock.is_action_triggered ? '🔥 异动' : '静默' }}
                  </span>
                </template>
                <!-- 筹码真空度 / 安全边际（埋伏模式显示原始数值） -->
                <template v-else-if="['chip_vacuum', 'safety_margin'].includes(col.key)">
                  <span class="text-sm font-mono text-gray-700">
                    {{ stock[col.key] ?? '--' }}
                  </span>
                </template>
                <!-- 预期逻辑 -->
                <template v-else-if="col.key === 'expected_logic'">
                  <span class="text-sm text-gray-600 truncate max-w-[200px] inline-block" :title="stock.expected_logic">
                    {{ stock.expected_logic || '-' }}
                  </span>
                </template>
                <!-- 埋伏日期 -->
                <template v-else-if="col.key === 'ambush_add_date'">
                  <span class="text-sm text-gray-500 font-mono">{{ stock.ambush_add_date || '-' }}</span>
                </template>
                <!-- 通用数值列 -->
                <template v-else>
                  <span class="text-sm text-gray-600">{{ stock[col.key] ?? '-' }}</span>
                </template>
              </td>
              <!-- 准入状态（仅正常模式） -->
              <td v-if="mode !== 'ambush'" class="px-3 py-3 whitespace-nowrap">
                <div
                  class="flex items-center space-x-1"
                  :title="stock.reject_reason || '准入通过'"
                >
                  <template v-if="stock.rejected">
                    <span class="text-red-500">❌</span>
                    <span class="text-xs text-gray-500">{{ getRejectShort(stock.reject_reason) }}</span>
                  </template>
                  <template v-else>
                    <span class="text-green-500">✓</span>
                    <div class="flex space-x-0.5">
                      <span v-if="stock.trend_baseline" class="w-1.5 h-1.5 rounded-full bg-green-400" :title="getStrategyFieldLabel('trend_baseline')"></span>
                      <span v-if="stock.chip_vacuum" class="w-1.5 h-1.5 rounded-full bg-blue-400" :title="getStrategyFieldLabel('chip_vacuum')"></span>
                      <span v-if="stock.kline_body" class="w-1.5 h-1.5 rounded-full bg-yellow-400" :title="getStrategyFieldLabel('kline_body')"></span>
                      <span v-if="stock.liquidity_base" class="w-1.5 h-1.5 rounded-full bg-purple-400" :title="getStrategyFieldLabel('liquidity_base')"></span>
                      <span v-if="stock.safety_margin" class="w-1.5 h-1.5 rounded-full bg-orange-400" :title="getStrategyFieldLabel('safety_margin')"></span>
                    </div>
                  </template>
                </div>
              </td>
              <!-- 操作列 -->
              <td class="px-3 py-3 whitespace-nowrap">
                <div class="flex items-center space-x-1">
                  <button
                    @click.stop="toggleWatchlist(stock)"
                    class="text-sm px-2 py-1 rounded transition-colors"
                    :class="isInWatchlist(stock.ts_code)
                      ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
                    title="加入自选股"
                  >
                    {{ isInWatchlist(stock.ts_code) ? '★' : '☆' }}
                  </button>
                  <button
                    @click.stop="goToReview(stock)"
                    class="text-sm px-2 py-1 rounded transition-colors bg-gray-100 text-gray-600 hover:bg-blue-100 hover:text-blue-700"
                    title="记录复盘"
                  >
                    📝
                  </button>
                  <!-- 埋伏池模式下的操作按钮 -->
                  <template v-if="mode === 'ambush'">
                    <button
                      v-if="isInAmbushPool(stock.ts_code)"
                      @click.stop="removeFromAmbush(stock)"
                      class="text-sm px-2 py-1 rounded transition-colors bg-red-100 text-red-600 hover:bg-red-200"
                      title="逻辑证伪/移出"
                    >
                      ❌
                    </button>
                    <button
                      v-else
                      @click.stop="addToAmbushPool(stock)"
                      class="text-sm px-2 py-1 rounded transition-colors bg-emerald-100 text-emerald-600 hover:bg-emerald-200"
                      title="添加到埋伏池"
                    >
                      ➕
                    </button>
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- 统计 -->
      <div class="px-4 py-3 bg-gray-50 border-t flex justify-between items-center">
        <span class="text-sm text-gray-500">
          <template v-if="searchQuery">
            全量 {{ picks.length }} 只，展示 {{ filteredPicks.length }} 只，准入通过 {{ filteredPassedCount }} 只
          </template>
          <template v-else>
            全量 {{ picks.length }} 只，展示 {{ filteredPicks.length }} 只，准入通过 {{ passedCount }} 只
          </template>
        </span>
        <div class="flex items-center space-x-2">
          <span v-if="lastUpdated" class="text-xs text-gray-400">
            更新于 {{ formatTime(lastUpdated) }}
          </span>
          <button
            @click="fetchPicks(true)"
            :disabled="loading"
            class="text-xs px-2 py-1 bg-white border rounded hover:bg-gray-50 disabled:opacity-50"
          >
            刷新
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { picksApi, stockApi } from '@/api'
import { ambushApi } from '@/api/ambush'
import { useWatchlistStore } from '@/stores/watchlist'
import { useReviewStore } from '@/stores/review'
import Loading from '@/components/Loading.vue'
import Error from '@/components/Error.vue'
import Empty from '@/components/Empty.vue'
import { getRejectReasonLabel, getStrategyFieldLabel } from '@/constants/strategyFields'
import {
  buildPicksCsv,
  buildPicksExportPayload,
  getPicksExportFilename,
} from '@/utils/picksExport'

const router = useRouter()
const watchlistStore = useWatchlistStore()
const reviewStore = useReviewStore()

const loading = ref(false)
const error = ref('')
const errorType = ref('unknown')
const errorDetails = ref('')
const picks = ref([])
const tradeDate = ref('')
const sortKey = ref('final_score')
const sortOrder = ref('desc')
const lastUpdated = ref(null)
const searchQuery = ref('')
const searchResults = ref([]) // 存储API搜索结果
const isSearching = ref(false)
const mode = ref('normal') // 'normal' 或 'ambush'

const columns = computed(() => {
  if (mode.value === 'ambush') {
    return [
      { key: 'name', title: '股票' },
      { key: 'industry', title: '行业' },
      { key: 'chip_vacuum', title: '筹码真空度' },
      { key: 'safety_margin', title: '安全边际' },
      { key: 'expected_logic', title: '预期逻辑' },
      { key: 'liquidity_base', title: '量能活跃' },
      { key: 'ambush_add_date', title: '埋伏日期' }
    ]
  }
  return [
    { key: 'name', title: '股票' },
    { key: 'industry', title: '行业' },
    { key: 'pct_chg', title: getStrategyFieldLabel('pct_chg') },
    { key: 'turnover_rate', title: getStrategyFieldLabel('turnover_rate') },
    { key: 'volume_ratio', title: getStrategyFieldLabel('volume_ratio') },
    { key: 'winner_rate', title: getStrategyFieldLabel('winner_rate') },
    { key: 'final_score', title: getStrategyFieldLabel('final_score') },
    { key: 'top_list_3d', title: '标签' }
  ]
})

const visiblePicks = computed(() => {
  // 埋伏池模式不做分数过滤，正常模式仅显示 95 分及以上
  if (mode.value === 'ambush') return picks.value
  return picks.value.filter(stock => (stock.final_score || 0) >= 95)
})

// 监听搜索词变化，调用API搜索
watch(searchQuery, async (newQuery) => {
  if (!newQuery.trim()) {
    searchResults.value = []
    return
  }
  
  isSearching.value = true
  try {
    const res = await stockApi.batchSearch([newQuery.trim()])
    searchResults.value = res?.items || []
  } catch (err) {
    console.error('搜索股票失败:', err)
    searchResults.value = []
  } finally {
    isSearching.value = false
  }
})

// 搜索过滤（搜索整个 picks 数组，并合并API搜索结果）
const filteredPicks = computed(() => {
  // 如果有搜索词，搜索整个 picks 数组并合并API结果
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.trim().toLowerCase()
    
    // 1. 从 picks 数组中搜索匹配的股票
    const matchedFromPicks = picks.value.filter(stock => {
      const code = stock.ts_code?.toLowerCase() || ''
      const name = stock.name?.toLowerCase() || ''
      const conceptText = stock.concept_text?.toLowerCase() || ''
      return code.includes(query) || name.includes(query) || conceptText.includes(query)
    })
    
    // 2. 从 API 搜索结果中过滤掉已经在 picks 中的股票
    const matchedFromApi = searchResults.value.filter(apiStock => {
      return !matchedFromPicks.some(pickStock => pickStock.ts_code === apiStock.ts_code)
    })
    
    // 3. 将 API 搜索结果转换为与 picks 数组兼容的格式
    const convertedApiStocks = matchedFromApi.map(apiStock => ({
      ts_code: apiStock.ts_code,
      name: apiStock.name,
      industry: apiStock.industry || '',
      concept_names: apiStock.concept_names || [],
      concept_text: apiStock.concept_text || '',
      // 策略字段设为 null 或默认值
      final_score: null,
      pct_chg: null,
      turnover_rate: null,
      volume_ratio: null,
      winner_rate: null,
      upper_space: null,
      vol_score: null,
      trend_baseline: null,
      chip_vacuum: null,
      kline_body: null,
      liquidity_base: null,
      safety_margin: null,
      top_list_3d: null,
      st_risk: null,
      rejected: null,
      reject_reason: null,
      is_action_triggered: false
    }))
    
    // 4. 合并结果
    return [...matchedFromPicks, ...convertedApiStocks]
  }
  
  // 没有搜索词时，使用 visiblePicks（分数过滤后的数据）
  return visiblePicks.value
})

const sortedPicks = computed(() => {
  const list = [...filteredPicks.value]
  list.sort((a, b) => {
    let va = a[sortKey.value]
    let vb = b[sortKey.value]
    
    if (typeof va === 'string') {
      va = va.toLowerCase()
      vb = vb.toLowerCase()
    }
    
    if (va < vb) return sortOrder.value === 'asc' ? -1 : 1
    if (va > vb) return sortOrder.value === 'asc' ? 1 : -1
    return 0
  })
  return list
})

const fullPassedCount = computed(() => {
  return picks.value.filter(s => !s.rejected).length
})

const passedCount = computed(() => {
  return visiblePicks.value.filter(s => !s.rejected).length
})

const filteredPassedCount = computed(() => {
  return filteredPicks.value.filter(s => !s.rejected).length
})

const modeLabel = computed(() => {
  return mode.value === 'ambush' ? '预期埋伏池' : '阻力最小爆发模型'
})

const emptyState = computed(() => {
  if (mode.value === 'ambush') {
    return {
      icon: '🥷',
      title: '暂无埋伏池数据',
      description: '可在爆发右侧列表中选择股票加入埋伏池',
    }
  }
  return {
    icon: '📊',
    title: '暂无选股数据',
    description: '请检查后端数据更新状态',
  }
})

function isInWatchlist(tsCode) {
  return watchlistStore.isInWatchlist(tsCode)
}

function isInAmbushPool(tsCode) {
  return picks.value.some(stock => stock.ts_code === tsCode)
}

function toggleWatchlist(stock) {
  const tsCode = stock.ts_code
  if (!tsCode) return

  if (isInWatchlist(tsCode)) {
    watchlistStore.remove(tsCode)
  } else {
    watchlistStore.add({
      tsCode,
      name: stock.name,
      industry: stock.industry,
      conceptNames: stock.concept_names || [],
      conceptText: stock.concept_text || ''
    })
  }
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
  if (score > 0) return 'text-gray-600'
  return 'text-gray-400'
}

function formatPercent(val) {
  if (val == null) return '-'
  const sign = val > 0 ? '+' : ''
  return `${sign}${val.toFixed(2)}%`
}

function formatNumber(val) {
  if (val == null) return '-'
  return val.toFixed(2)
}

function formatTime(date) {
  if (!date) return '-'
  const d = new Date(date)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
}

function getRejectShort(reason) {
  return getRejectReasonLabel(reason)
}

function getVisibleConcepts(stock) {
  return (stock.concept_names || []).slice(0, 3)
}

function getConceptOverflow(stock) {
  return Math.max((stock.concept_names || []).length - 3, 0)
}

function goToDetail(tsCode) {
  router.push(`/stock/${tsCode}`)
}

function goToReview(stock) {
  router.push({
    path: '/review',
    query: {
      tsCode: stock.ts_code,
      name: stock.name
    }
  })
}

async function fetchPicks(forceRefresh = false) {
  loading.value = true
  error.value = ''
  errorType.value = 'unknown'
  errorDetails.value = ''
  
  try {
    let data
    if (mode.value === 'ambush') {
      const params = { is_ambush: true }
      data = forceRefresh
        ? await picksApi.refreshPicks(params)
        : await picksApi.getPicks(params)
    } else {
      data = forceRefresh 
        ? await picksApi.refreshPicks()
        : await picksApi.getPicks()
    }
    picks.value = data || []
    if (data && data.length > 0) {
      tradeDate.value = data[0].trade_date || ''
    }
    lastUpdated.value = new Date()
  } catch (err) {
    error.value = err.message
    errorType.value = err.type || 'unknown'
    errorDetails.value = err.original?.message || ''
  } finally {
    loading.value = false
  }
}

onMounted(fetchPicks)

// 模式切换函数
function switchMode(newMode) {
  if (mode.value === newMode) return
  mode.value = newMode
  // 切换模式后重新获取数据
  fetchPicks()
}

// 一键剔除逻辑
async function removeFromAmbush(stock) {
  if (!confirm(`确认将 ${stock.name} 从埋伏池移出？\n原因：逻辑证伪`)) {
    return
  }
  
  try {
    await ambushApi.removeFromAmbushPool(stock.ts_code)
    // 刷新列表
    await fetchPicks(true)
    alert('已移出埋伏池')
  } catch (err) {
    alert(`移出失败: ${err.message}`)
  }
}

// 添加到埋伏池
async function addToAmbushPool(stock) {
  // 用概念题材作为默认预填值，降低填写负担
  const defaultLogic = stock.concept_text ? `概念题材：${stock.concept_text}` : ''
  const expectedLogic = prompt(
    `📝 ${stock.name}（${stock.ts_code}）\n请输入埋伏预期逻辑（必填）：`,
    defaultLogic
  )
  if (expectedLogic === null) return // 用户点取消

  // 前端必填校验，与后端 min_length=1 对齐
  if (!expectedLogic.trim()) {
    alert('预期逻辑不能为空，请填写后再添加。')
    return
  }

  try {
    await ambushApi.addToAmbushPool(stock.ts_code, expectedLogic.trim())
    // 刷新列表
    await fetchPicks(true)
    alert(`✅ 已将 ${stock.name} 添加到埋伏池`)
  } catch (err) {
    alert(`添加失败: ${err.message}`)
  }
}

// ========== 导出功能 ==========

function getExportFilename(ext) {
  return getPicksExportFilename(ext, tradeDate.value, mode.value)
}

async function saveTextFile(filename, content, mimeType) {
  if (window.pywebview?.api?.save_text_file) {
    try {
      const result = await window.pywebview.api.save_text_file(filename, content)
      if (result?.saved) return
      if (result?.error) throw new Error(result.error)
      return
    } catch (err) {
      console.error('桌面保存失败，切换浏览器下载:', err)
    }
  }

  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function exportJSON() {
  if (!picks.value.length) return
  
  const data = buildPicksExportPayload({
    rows: picks.value,
    mode: mode.value,
    tradeDate: tradeDate.value,
    passed: fullPassedCount.value,
  })
  await saveTextFile(
    getExportFilename('json'),
    JSON.stringify(data, null, 2),
    'application/json;charset=utf-8'
  )
}

async function exportCSV() {
  if (!picks.value.length) return
  
  const csvContent = buildPicksCsv({
    rows: picks.value,
    mode: mode.value,
    tradeDate: tradeDate.value,
    getStrategyFieldLabel,
    getRejectReasonLabel,
  })
  await saveTextFile(
    getExportFilename('csv'),
    '\uFEFF' + csvContent,
    'text/csv;charset=utf-8'
  )
}
</script>
