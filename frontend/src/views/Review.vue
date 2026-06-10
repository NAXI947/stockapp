<template>
  <div>
    <div class="mb-6">
      <h1 class="text-xl font-bold text-gray-900">策略复盘</h1>
      <p class="text-sm text-gray-500 mt-1">
        记录分析判断，追踪策略效果，形成决策闭环
      </p>
    </div>
    
    <!-- 快速添加复盘（从其他页面跳转时显示） -->
    <div v-if="showQuickAdd" class="bg-blue-50 rounded-lg p-4 mb-6 border border-blue-100">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-medium text-blue-900">
            为 {{ quickAddName }} ({{ quickAddCode }}) 添加复盘记录
          </h3>
          <p class="text-sm text-blue-600 mt-1">
            记录你当前的分析判断，方便后续对比验证
          </p>
        </div>
        <button
          @click="startQuickAdd"
          class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm font-medium"
        >
          开始记录
        </button>
      </div>
    </div>
    
    <!-- 统计卡片 -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">总记录数</p>
        <p class="text-2xl font-bold text-gray-900">{{ stats.total }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">纳入观察</p>
        <p class="text-2xl font-bold text-blue-600">{{ stats.watching }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">计划买入</p>
        <p class="text-2xl font-bold text-green-600">{{ stats.planBuy }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs text-gray-500">已复盘</p>
        <p class="text-2xl font-bold text-purple-600">{{ stats.reviewed }}</p>
      </div>
    </div>
    
    <!-- 复盘列表 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="px-4 py-3 border-b flex justify-between items-center">
        <h3 class="font-medium text-gray-900">复盘记录</h3>
        <div class="flex items-center space-x-2">
          <select
            v-model="filterStatus"
            class="text-sm border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">全部</option>
            <option value="watching">纳入观察</option>
            <option value="plan_buy">计划买入</option>
            <option value="reviewed">已复盘</option>
          </select>
          <button
            @click="showAddModal = true"
            class="text-sm px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            + 添加
          </button>
        </div>
      </div>
      
      <!-- 空状态 -->
      <Empty
        v-if="!filteredReviews.length"
        icon="📝"
        title="暂无复盘记录"
        description="点击右上角添加按钮开始记录"
      />
      
      <!-- 列表 -->
      <div v-else class="divide-y divide-gray-200">
        <div
          v-for="review in filteredReviews"
          :key="review.id"
          class="p-4 hover:bg-gray-50 transition-colors"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center space-x-2">
                <h4 class="font-medium text-gray-900">{{ review.name }}</h4>
                <span class="text-sm text-gray-500">{{ review.tsCode }}</span>
                <span class="text-xs text-gray-400">{{ formatDate(review.createdAt) }}</span>
              </div>
              <div v-if="review.industry || review.conceptNames?.length" class="mt-2 flex flex-wrap gap-1.5">
                <span
                  v-if="review.industry"
                  class="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
                >
                  {{ review.industry }}
                </span>
                <span
                  v-for="concept in getVisibleConcepts(review)"
                  :key="`${review.id}-${concept}`"
                  class="text-xs bg-sky-100 text-sky-700 px-2 py-0.5 rounded"
                  :title="review.conceptText || concept"
                >
                  {{ concept }}
                </span>
                <span
                  v-if="getConceptOverflow(review) > 0"
                  class="text-xs bg-sky-50 text-sky-600 px-2 py-0.5 rounded"
                  :title="review.conceptText || ''"
                >
                  +{{ getConceptOverflow(review) }}
                </span>
              </div>
              
              <!-- 当时策略信号 -->
              <div class="mt-2 flex items-center space-x-4 text-sm">
                <span v-if="review.strategyScore" class="text-gray-600">
                  策略分: <span class="font-mono font-medium" :class="getScoreClass(review.strategyScore)">{{ review.strategyScore }}</span>
                </span>
                <span v-if="review.pctChg != null" class="text-gray-600">
                  当日涨跌: <span class="font-mono" :class="review.pctChg >= 0 ? 'text-up' : 'text-down'">{{ formatPercent(review.pctChg) }}</span>
                </span>
              </div>
              
              <!-- 决策标记 -->
              <div class="mt-2 flex items-center space-x-2">
                <span 
                  v-if="review.isWatching" 
                  class="inline-block px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded"
                >
                  纳入观察
                </span>
                <span 
                  v-if="review.planBuy" 
                  class="inline-block px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded"
                >
                  计划买入
                </span>
                <span 
                  v-if="review.isReviewed" 
                  class="inline-block px-2 py-0.5 text-xs bg-purple-100 text-purple-700 rounded"
                >
                  已复盘
                </span>
              </div>
              
              <!-- 主观判断 -->
              <p v-if="review.judgment" class="mt-2 text-sm text-gray-700 bg-gray-50 p-2 rounded">
                {{ review.judgment }}
              </p>
              
              <!-- 复盘结论 -->
              <div v-if="review.reviewConclusion" class="mt-2 text-sm text-purple-700 bg-purple-50 p-2 rounded">
                <span class="font-medium">复盘结论：</span>{{ review.reviewConclusion }}
              </div>
            </div>
            
            <!-- 操作按钮 -->
            <div class="flex items-center space-x-2 ml-4">
              <button
                v-if="!review.isReviewed"
                @click="openReviewModal(review)"
                class="text-sm px-3 py-1 bg-purple-500 text-white rounded hover:bg-purple-600"
              >
                复盘
              </button>
              <button
                @click="viewDetail(review)"
                class="text-sm px-3 py-1 border rounded hover:bg-gray-50"
              >
                查看
              </button>
              <button
                @click="deleteReview(review.id)"
                class="text-sm px-3 py-1 text-red-500 hover:bg-red-50 rounded"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 添加复盘弹窗 -->
    <div v-if="showAddModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <div class="p-4 border-b flex justify-between items-center">
          <h3 class="font-medium text-gray-900">添加复盘记录</h3>
          <button @click="showAddModal = false" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div class="p-4 space-y-4">
          <!-- 股票代码 -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票代码</label>
            <input
              v-model="newReview.tsCode"
              type="text"
              placeholder="如: 000001.SZ"
              class="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <!-- 决策选项 -->
          <div class="flex space-x-4">
            <label class="flex items-center space-x-2 cursor-pointer">
              <input v-model="newReview.isWatching" type="checkbox" class="rounded text-blue-500" />
              <span class="text-sm">纳入观察</span>
            </label>
            <label class="flex items-center space-x-2 cursor-pointer">
              <input v-model="newReview.planBuy" type="checkbox" class="rounded text-blue-500" />
              <span class="text-sm">计划买入</span>
            </label>
          </div>
          
          <!-- 主观判断 -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">主观判断</label>
            <textarea
              v-model="newReview.judgment"
              rows="3"
              placeholder="记录你当时的分析思路..."
              class="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            ></textarea>
          </div>
          
          <!-- 当前策略信息（自动获取） -->
          <div v-if="newReview.strategyScore" class="bg-gray-50 p-3 rounded text-sm">
            <p class="text-gray-500 mb-1">当前策略信号</p>
            <div class="flex space-x-4">
              <span>策略分: <strong :class="getScoreClass(newReview.strategyScore)">{{ newReview.strategyScore }}</strong></span>
              <span>涨跌: <strong :class="newReview.pctChg >= 0 ? 'text-up' : 'text-down'">{{ formatPercent(newReview.pctChg) }}</strong></span>
            </div>
          </div>
        </div>
        <div class="p-4 border-t flex justify-end space-x-2">
          <button
            @click="showAddModal = false"
            class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded"
          >
            取消
          </button>
          <button
            @click="addReview"
            :disabled="!newReview.tsCode || adding"
            class="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {{ adding ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- 复盘结论弹窗 -->
    <div v-if="showReviewModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg max-w-lg w-full">
        <div class="p-4 border-b flex justify-between items-center">
          <h3 class="font-medium text-gray-900">添加复盘结论</h3>
          <button @click="showReviewModal = false" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div class="p-4 space-y-4">
          <div class="bg-gray-50 p-3 rounded">
            <p class="text-sm text-gray-500">{{ currentReview?.name }} ({{ currentReview?.tsCode }})</p>
            <p class="text-xs text-gray-400">{{ formatDate(currentReview?.createdAt) }}</p>
            <div v-if="currentReview?.industry || currentReview?.conceptNames?.length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-if="currentReview?.industry"
                class="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
              >
                {{ currentReview?.industry }}
              </span>
              <span
                v-for="concept in getVisibleConcepts(currentReview)"
                :key="`modal-${currentReview?.id}-${concept}`"
                class="text-xs bg-sky-100 text-sky-700 px-2 py-0.5 rounded"
                :title="currentReview?.conceptText || concept"
              >
                {{ concept }}
              </span>
              <span
                v-if="getConceptOverflow(currentReview) > 0"
                class="text-xs bg-sky-50 text-sky-600 px-2 py-0.5 rounded"
                :title="currentReview?.conceptText || ''"
              >
                +{{ getConceptOverflow(currentReview) }}
              </span>
            </div>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">复盘结论</label>
            <textarea
              v-model="reviewConclusion"
              rows="4"
              placeholder="记录后续走势和你的反思..."
              class="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            ></textarea>
          </div>
        </div>
        <div class="p-4 border-t flex justify-end space-x-2">
          <button
            @click="showReviewModal = false"
            class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded"
          >
            取消
          </button>
          <button
            @click="saveReviewConclusion"
            :disabled="!reviewConclusion"
            class="px-4 py-2 text-sm bg-purple-500 text-white rounded hover:bg-purple-600 disabled:opacity-50"
          >
            保存复盘
          </button>
        </div>
      </div>
    </div>
    
    <!-- 详情弹窗 -->
    <div v-if="showDetailModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <div class="p-4 border-b flex justify-between items-center">
          <h3 class="font-medium text-gray-900">复盘详情</h3>
          <button @click="showDetailModal = false" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div v-if="currentReview" class="p-4 space-y-4">
          <!-- 基本信息 -->
          <div class="flex items-center justify-between">
            <div>
              <h4 class="font-medium text-gray-900">{{ currentReview.name }}</h4>
              <p class="text-sm text-gray-500">{{ currentReview.tsCode }}</p>
            </div>
            <span class="text-sm text-gray-400">{{ formatDate(currentReview.createdAt) }}</span>
          </div>
          <div v-if="currentReview.industry || currentReview.conceptNames?.length" class="flex flex-wrap gap-1.5">
            <span
              v-if="currentReview.industry"
              class="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
            >
              {{ currentReview.industry }}
            </span>
            <span
              v-for="concept in getVisibleConcepts(currentReview)"
              :key="`detail-${currentReview.id}-${concept}`"
              class="text-xs bg-sky-100 text-sky-700 px-2 py-0.5 rounded"
              :title="currentReview.conceptText || concept"
            >
              {{ concept }}
            </span>
            <span
              v-if="getConceptOverflow(currentReview) > 0"
              class="text-xs bg-sky-50 text-sky-600 px-2 py-0.5 rounded"
              :title="currentReview.conceptText || ''"
            >
              +{{ getConceptOverflow(currentReview) }}
            </span>
          </div>
          
          <!-- 当时策略信号 -->
          <div class="bg-gray-50 p-3 rounded">
            <p class="text-xs text-gray-500 mb-2">当时策略信号</p>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>策略分: <span :class="getScoreClass(currentReview.strategyScore)">{{ currentReview.strategyScore || '-' }}</span></div>
              <div>涨跌: <span :class="currentReview.pctChg >= 0 ? 'text-up' : 'text-down'">{{ formatPercent(currentReview.pctChg) }}</span></div>
              <div>换手率: {{ formatNumber(currentReview.turnoverRate) }}%</div>
              <div>量比: {{ formatNumber(currentReview.volumeRatio) }}</div>
            </div>
          </div>
          
          <!-- 当时决策 -->
          <div class="flex items-center space-x-2">
            <span v-if="currentReview.isWatching" class="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded">纳入观察</span>
            <span v-if="currentReview.planBuy" class="px-2 py-1 text-xs bg-green-100 text-green-700 rounded">计划买入</span>
          </div>
          
          <!-- 主观判断 -->
          <div v-if="currentReview.judgment">
            <p class="text-xs text-gray-500 mb-1">主观判断</p>
            <p class="text-sm text-gray-700 bg-gray-50 p-2 rounded">{{ currentReview.judgment }}</p>
          </div>
          
          <!-- 复盘结论 -->
          <div v-if="currentReview.reviewConclusion">
            <p class="text-xs text-gray-500 mb-1">复盘结论</p>
            <p class="text-sm text-purple-700 bg-purple-50 p-2 rounded">{{ currentReview.reviewConclusion }}</p>
          </div>
          
          <!-- 操作 -->
          <div class="flex space-x-2 pt-2">
            <button
              @click="goToStock(currentReview.tsCode)"
              class="flex-1 px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              查看股票详情
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useReviewStore } from '@/stores/review'
import { stockApi } from '@/api'
import Empty from '@/components/Empty.vue'

const route = useRoute()
const router = useRouter()
const reviewStore = useReviewStore()

// 弹窗状态
const showAddModal = ref(false)
const showReviewModal = ref(false)
const showDetailModal = ref(false)
const adding = ref(false)

// 筛选状态
const filterStatus = ref('all')

// 当前操作的复盘记录
const currentReview = ref(null)
const reviewConclusion = ref('')

// 快速添加（从其他页面跳转）
const quickAddCode = ref('')
const quickAddName = ref('')
const showQuickAdd = computed(() => quickAddCode.value && !reviewStore.hasReview(quickAddCode.value))

// 新复盘表单
const newReview = ref({
  tsCode: '',
  name: '',
  industry: '',
  conceptNames: [],
  conceptText: '',
  isWatching: true,
  planBuy: false,
  judgment: '',
  strategyScore: null,
  pctChg: null,
  turnoverRate: null,
  volumeRatio: null
})

// 统计
const stats = computed(() => {
  const list = reviewStore.list
  return {
    total: list.length,
    watching: list.filter(r => r.isWatching).length,
    planBuy: list.filter(r => r.planBuy).length,
    reviewed: list.filter(r => r.isReviewed).length
  }
})

// 筛选后的列表
const filteredReviews = computed(() => {
  let list = [...reviewStore.list]
  
  if (filterStatus.value === 'watching') {
    list = list.filter(r => r.isWatching && !r.isReviewed)
  } else if (filterStatus.value === 'plan_buy') {
    list = list.filter(r => r.planBuy && !r.isReviewed)
  } else if (filterStatus.value === 'reviewed') {
    list = list.filter(r => r.isReviewed)
  }
  
  // 按时间倒序
  list.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
  
  return list
})

// 工具函数
function getScoreClass(score) {
  if (score >= 70) return 'text-green-600'
  if (score >= 50) return 'text-yellow-600'
  return 'text-gray-600'
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

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`
}

function getVisibleConcepts(stock) {
  return (stock?.conceptNames || []).slice(0, 4)
}

function getConceptOverflow(stock) {
  return Math.max((stock?.conceptNames || []).length - 4, 0)
}

// 操作函数
function startQuickAdd() {
  newReview.value.tsCode = quickAddCode.value
  newReview.value.name = quickAddName.value
  fetchStockData(newReview.value.tsCode)
  showAddModal.value = true
}

async function fetchStockData(tsCode) {
  try {
    const data = await stockApi.getDetail(tsCode)
    if (data) {
      newReview.value.name = data.name || newReview.value.name
      newReview.value.industry = data.industry || ''
      newReview.value.conceptNames = data.concept_names || []
      newReview.value.conceptText = data.concept_text || ''
      newReview.value.strategyScore = data.final_score
      newReview.value.pctChg = data.pct_chg
      newReview.value.turnoverRate = data.turnover_rate
      newReview.value.volumeRatio = data.volume_ratio
    }
  } catch (err) {
    console.error('获取股票数据失败:', err)
  }
}

async function addReview() {
  if (!newReview.value.tsCode) return
  
  adding.value = true
  
  // 如果没有获取到数据，尝试获取
  if (newReview.value.strategyScore == null) {
    await fetchStockData(newReview.value.tsCode)
  }
  
  reviewStore.add({
    tsCode: newReview.value.tsCode,
    name: newReview.value.name || newReview.value.tsCode,
    industry: newReview.value.industry,
    conceptNames: newReview.value.conceptNames,
    conceptText: newReview.value.conceptText,
    isWatching: newReview.value.isWatching,
    planBuy: newReview.value.planBuy,
    judgment: newReview.value.judgment,
    strategyScore: newReview.value.strategyScore,
    pctChg: newReview.value.pctChg,
    turnoverRate: newReview.value.turnoverRate,
    volumeRatio: newReview.value.volumeRatio
  })
  
  // 重置表单
  newReview.value = {
    tsCode: '',
    name: '',
    industry: '',
    conceptNames: [],
    conceptText: '',
    isWatching: true,
    planBuy: false,
    judgment: '',
    strategyScore: null,
    pctChg: null,
    turnoverRate: null,
    volumeRatio: null
  }
  
  adding.value = false
  showAddModal.value = false
}

function openReviewModal(review) {
  currentReview.value = review
  reviewConclusion.value = review.reviewConclusion || ''
  showReviewModal.value = true
}

function saveReviewConclusion() {
  if (!currentReview.value || !reviewConclusion.value) return
  
  reviewStore.update(currentReview.value.id, {
    reviewConclusion: reviewConclusion.value,
    isReviewed: true,
    reviewedAt: new Date().toISOString()
  })
  
  reviewConclusion.value = ''
  currentReview.value = null
  showReviewModal.value = false
}

function viewDetail(review) {
  currentReview.value = review
  showDetailModal.value = true
}

function deleteReview(id) {
  if (confirm('确定删除这条复盘记录吗？')) {
    reviewStore.remove(id)
  }
}

function goToStock(tsCode) {
  showDetailModal.value = false
  router.push(`/stock/${tsCode}`)
}

// 监听股票代码输入，自动获取数据
watch(() => newReview.value.tsCode, (val) => {
  if (val && val.length > 5 && newReview.value.strategyScore == null) {
    fetchStockData(val)
  }
})

onMounted(() => {
  // 检查是否有跳转参数
  if (route.query.tsCode) {
    quickAddCode.value = route.query.tsCode
    quickAddName.value = route.query.name || route.query.tsCode
  }
})
</script>
