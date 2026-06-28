<template>
  <div>
    <!-- 返回按钮 -->
    <div class="mb-4">
      <button
        @click="$router.back()"
        class="text-sm text-gray-600 hover:text-gray-900 flex items-center"
      >
        ← 返回
      </button>
    </div>

    <!-- 指标分页 -->
    <div
      class="mb-6 inline-flex rounded-lg bg-gray-100 p-1 shadow-inner"
      role="tablist"
      aria-label="个股指标切换"
    >
      <button
        type="button"
        role="tab"
        :aria-selected="!isSniper"
        :disabled="loading"
        @click="switchIndicator('breakout')"
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:cursor-wait"
        :class="!isSniper
          ? 'bg-white text-blue-700 shadow-sm'
          : 'text-gray-600 hover:text-gray-900'"
      >
        🔥 爆发右侧
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="isSniper"
        :disabled="loading"
        @click="switchIndicator('sniper')"
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:cursor-wait"
        :class="isSniper
          ? 'bg-white text-purple-700 shadow-sm'
          : 'text-gray-600 hover:text-gray-900'"
      >
        🎯 极简狙击手
      </button>
    </div>
    
    <!-- 加载中 -->
    <Loading v-if="loading" />
    
    <!-- 错误 -->
    <Error
      v-else-if="error"
      :type="errorType"
      :message="error"
      :details="errorDetails"
      show-back
      @retry="fetchData"
    />
    
    <!-- 股票详情 -->
    <div v-else-if="detail" class="space-y-6">
      <!-- 头部信息 -->
      <div class="bg-white rounded-lg shadow p-4">
        <div class="flex items-start justify-between">
          <div>
            <h1 class="text-xl font-bold text-gray-900">{{ detail.name }}</h1>
            <p class="text-sm text-gray-500">{{ tsCode }}</p>
            <div v-if="detail.industry || detail.concept_names?.length" class="mt-3 flex flex-wrap gap-2">
              <span
                v-if="detail.industry"
                class="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded"
              >
                {{ detail.industry }}
              </span>
              <span
                v-for="concept in visibleConcepts"
                :key="concept"
                class="text-xs bg-sky-100 text-sky-700 px-2 py-1 rounded"
                :title="detail.concept_text || concept"
              >
                {{ concept }}
              </span>
              <span
                v-if="conceptOverflow > 0"
                class="text-xs bg-sky-50 text-sky-600 px-2 py-1 rounded"
                :title="detail.concept_text || ''"
              >
                +{{ conceptOverflow }}
              </span>
            </div>
          </div>
          <div class="flex items-center space-x-3">
            <span
              class="text-2xl font-mono font-bold"
              :class="detail.pct_chg >= 0 ? 'text-up' : 'text-down'"
            >
              {{ formatPercent(detail.pct_chg) }}
            </span>
            <button
              @click="toggleWatchlist"
              class="text-lg px-3 py-1 rounded transition-colors"
              :class="isInWatchlist
                ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
            >
              {{ isInWatchlist ? '★ 已关注' : '☆ 关注' }}
            </button>
            <button
              @click="goToReview"
              class="text-lg px-3 py-1 rounded transition-colors bg-gray-100 text-gray-600 hover:bg-blue-100 hover:text-blue-700"
              title="记录复盘"
            >
              📝 复盘
            </button>
          </div>
        </div>
        
        <!-- 关键指标 -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4 pt-4 border-t">
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('final_score') }}</p>
            <p
              class="text-lg font-mono font-bold"
              :class="getScoreClass(detail.final_score)"
            >
              {{ detail.final_score }}
            </p>
          </div>
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('turnover_rate') }}</p>
            <p class="text-lg font-mono">{{ formatNumber(detail.turnover_rate) }}%</p>
          </div>
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('volume_ratio') }}</p>
            <p class="text-lg font-mono">{{ formatNumber(detail.volume_ratio) }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('winner_rate') }}</p>
            <p class="text-lg font-mono">{{ formatNumber(detail.winner_rate) }}%</p>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4 pt-4 border-t">
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('chip_vacuum') }}</p>
            <p class="text-base font-mono">{{ formatFlag(detail.chip_vacuum) }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('safety_margin') }}</p>
            <p class="text-base font-mono">{{ formatFlag(detail.safety_margin) }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-500">{{ getStrategyFieldLabel('trend_baseline') }}</p>
            <p class="text-base font-mono">{{ formatFlag(detail.trend_baseline) }}</p>
          </div>
        </div>

        <!-- 7日总评分趋势可视化 -->
        <div v-if="indicatorHistory.length" class="mt-4 pt-4 border-t">
          <div>
            <p class="text-xs font-semibold text-gray-700 mb-2">
              7日总评分走势 ({{ isSniper ? '极简狙击手' : '爆发右侧' }})
            </p>
            <div class="flex items-center space-x-1 overflow-x-auto pb-1">
              <div
                v-for="h in indicatorHistory"
                :key="h.trade_date"
                class="flex flex-col items-center shrink-0 w-12"
              >
                <div class="text-[9px] text-gray-400 font-mono">{{ h.trade_date.slice(4) }}</div>
                <div
                  class="w-8 h-10 flex items-end justify-center bg-gray-50 rounded mt-0.5 border border-gray-100"
                  :title="`${h.trade_date}: ${h.final_score}分`"
                >
                  <div
                    class="w-4 rounded-t transition-all duration-300"
                    :class="h.final_score >= 70 ? 'bg-emerald-500' : (h.final_score >= 50 ? 'bg-yellow-500' : 'bg-gray-400')"
                    :style="`height: ${Math.max(10, (h.final_score / 100) * 100)}%`"
                  ></div>
                </div>
                <div class="text-[10px] font-semibold mt-0.5 font-mono" :class="getScoreClass(h.final_score)">
                  {{ h.final_score }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 评分拆解 -->
      <div class="bg-white rounded-lg shadow p-4">
        <div class="flex items-start justify-between gap-4 mb-4">
          <div>
            <h3 class="text-sm font-medium text-gray-700">{{ isSniper ? '极简狙击手评分拆解' : '策略评分拆解' }}</h3>
            <p class="text-xs text-gray-500 mt-1">展示各评分项规则分值与当前命中状态，总分以策略计算结果为准</p>
          </div>
          <div class="text-right">
            <p class="text-xs text-gray-500">总分</p>
            <p class="text-2xl font-mono font-bold" :class="getScoreClass(detail.final_score)">
              {{ detail.final_score ?? 0 }}
            </p>
          </div>
        </div>

        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div class="rounded-lg border border-gray-200 overflow-hidden">
            <div class="px-4 py-3 bg-gray-50 border-b">
              <div class="flex items-center justify-between">
                <span class="text-sm font-medium text-gray-700">基础评分</span>
                <span class="text-xs text-gray-500">满分 60</span>
              </div>
            </div>
            <div class="divide-y divide-gray-100">
              <div
                v-for="item in baseScoreItems"
                :key="item.key"
                class="px-4 py-3 flex items-start justify-between gap-4"
              >
                <div>
                  <p class="text-sm font-medium text-gray-900">{{ item.label }}</p>
                  <p class="text-xs text-gray-500 mt-1">{{ item.description }}</p>
                </div>
                <div class="text-right shrink-0">
                  <p class="text-sm font-mono font-semibold text-gray-900">{{ item.scoreLabel }}</p>
                  <p class="text-xs" :class="item.active ? 'text-green-600' : 'text-gray-400'">{{ item.ruleLabel }}</p>
                </div>
              </div>
            </div>
          </div>

          <div class="rounded-lg border border-gray-200 overflow-hidden">
            <div class="px-4 py-3 bg-gray-50 border-b">
              <div class="flex items-center justify-between">
                <span class="text-sm font-medium text-gray-700">{{ isSniper ? '动态加分' : '动能加分与风险' }}</span>
                <span class="text-xs text-gray-500">{{ isSniper ? '满分 40' : '满分 55，风险最多扣 20' }}</span>
              </div>
            </div>
            <div class="divide-y divide-gray-100">
              <div
                v-for="item in momentumScoreItems"
                :key="item.key"
                class="px-4 py-3 flex items-start justify-between gap-4"
              >
                <div>
                  <p class="text-sm font-medium text-gray-900">{{ item.label }}</p>
                  <p class="text-xs text-gray-500 mt-1">{{ item.description }}</p>
                </div>
                <div class="text-right shrink-0">
                  <p class="text-sm font-mono font-semibold text-gray-900">{{ item.scoreLabel }}</p>
                  <p class="text-xs" :class="item.active ? 'text-green-600' : (item.penalty ? 'text-red-600' : 'text-gray-400')">
                    {{ item.ruleLabel }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-4 rounded-lg bg-blue-50 border border-blue-100 px-4 py-3">
          <p class="text-sm text-blue-900" v-if="isSniper">
            已知基础分 {{ baseScoreSummary }}，动态分 {{ momentumScoreSummary }}，总分以策略结果 {{ detail.final_score ?? 0 }} 分为准
          </p>
          <p class="text-sm text-blue-900" v-else>
            已知基础分 {{ baseScoreSummary }}{{ chipScoreSummary }}，动能分 {{ momentumScoreSummary }}，风险项 {{ penaltyScoreSummary }}，总分以策略结果 {{ detail.final_score ?? 0 }} 分为准
          </p>
        </div>
      </div>

      <!-- 15个细分评分项 7天评分趋势 -->
      <div class="bg-white rounded-lg shadow p-4" v-if="indicatorHistory.length">
        <div class="flex items-start justify-between gap-4 mb-4">
          <div>
            <h3 class="text-sm font-semibold text-gray-900">15个细分指标 7天评分变动趋势</h3>
            <p class="text-xs text-gray-500 mt-1">可视化展示 15 个关键评分维度的 7 日内达成及最新命中情况</p>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          <div
            v-for="ind in detailIndicators"
            :key="ind.key"
            class="p-2.5 border border-gray-100 rounded-lg bg-gray-50/50 flex flex-col justify-between"
          >
            <div>
              <div class="flex justify-between items-start">
                <span class="text-xs font-semibold text-gray-800">{{ ind.label }}</span>
                <span
                  class="text-[10px] px-1 py-0.2 rounded font-mono"
                  :class="ind.latestActive ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-200 text-gray-500'"
                >
                  {{ ind.latestValue }}
                </span>
              </div>
              <p class="text-[10px] text-gray-400 mt-0.5 leading-tight">{{ ind.description }}</p>
            </div>

            <!-- 7天每日状态灯；主力控盘度使用原始无序度控制柱高、评分控制颜色 -->
            <div class="mt-2.5">
              <div v-if="ind.isChaos" class="flex items-end space-x-1 h-10">
                <div
                  v-for="(histVal, hidx) in ind.trend"
                  :key="hidx"
                  class="flex-1 h-10 flex items-end justify-center"
                >
                  <div
                    class="w-full max-w-3 rounded-t transition-all duration-200"
                    :class="chaosBarClass(histVal.score)"
                    :style="{ height: `${chaosBarHeight(histVal.value)}px` }"
                    :title="`${indicatorHistory[hidx]?.trade_date}: 无序度 ${histVal.value ?? '-'}，${histVal.score ?? 0}分`"
                  ></div>
                </div>
              </div>
              <div v-else class="flex space-x-1">
                <div
                  v-for="(histVal, hidx) in ind.trend"
                  :key="hidx"
                  class="flex-1 text-center"
                >
                  <div
                    class="h-2 rounded-xs transition-colors duration-200"
                    :class="histVal ? (ind.isPenalty ? 'bg-red-500' : 'bg-emerald-500') : 'bg-gray-200'"
                    :title="`${indicatorHistory[hidx]?.trade_date}: ${histVal ? '达成' : '未达成'}`"
                  ></div>
                </div>
              </div>
              <div class="flex justify-between text-[8px] text-gray-400 mt-0.5 font-mono leading-none">
                <span>{{ indicatorHistory[0]?.trade_date.slice(4) }}</span>
                <span>{{ indicatorHistory[indicatorHistory.length - 1]?.trade_date.slice(4) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        class="rounded-lg border px-4 py-3"
        :class="summaryToneClass"
      >
        <div class="flex items-center justify-between gap-4">
          <div>
            <h3 class="text-sm font-medium">评分结论摘要</h3>
            <p class="text-sm mt-1">{{ scoreSummaryText }}</p>
          </div>
          <span
            class="text-xs px-2 py-1 rounded-full shrink-0"
            :class="summaryBadgeClass"
          >
            {{ detail.rejected ? '未通过准入' : '准入通过' }}
          </span>
        </div>
      </div>
      
      <!-- 历史成交数据 -->
      <div class="bg-white rounded-lg shadow p-4">
        <h3 class="text-sm font-medium text-gray-700 mb-3">历史成交数据</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">日期</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">开盘</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">最高</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">最低</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">收盘</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">涨跌幅</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">涨跌额</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">成交量(万手)</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">成交额(亿)</th>
                <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">{{ getStrategyFieldLabel('turnover_rate') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              <tr v-for="(item, index) in klineTableData" :key="item.trade_date">
                <td class="px-3 py-2 text-center font-mono">{{ item.trade_date }}</td>
                <td class="px-3 py-2 text-center font-mono">{{ formatPrice(item.open) }}</td>
                <td class="px-3 py-2 text-center font-mono">{{ formatPrice(item.high) }}</td>
                <td class="px-3 py-2 text-center font-mono">{{ formatPrice(item.low) }}</td>
                <td class="px-3 py-2 text-center font-mono">{{ formatPrice(item.close) }}</td>
                <td class="px-3 py-2 text-center font-mono" :class="item.pct_chg >= 0 ? 'text-up' : 'text-down'">
                  {{ formatPercent(item.pct_chg) }}
                </td>
                <td class="px-3 py-2 text-center font-mono" :class="item.change >= 0 ? 'text-up' : 'text-down'">
                  {{ formatChange(item.change) }}
                </td>
                <td class="px-3 py-2 text-center font-mono">{{ formatVol(item.vol) }}</td>
                <td class="px-3 py-2 text-center font-mono">{{ formatAmount(item.amount) }}</td>
                <td class="px-3 py-2 text-center font-mono">{{ formatNumber(item.turnover_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      
      <!-- 筹码与风险 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="bg-white rounded-lg shadow p-4">
          <h3 class="text-sm font-medium text-gray-700 mb-3">筹码分布</h3>
          <div class="space-y-2 text-sm">
            <div class="flex justify-between">
              <span class="text-gray-500">50%成本</span>
              <span class="font-mono">{{ formatPrice(detail.cost_50) }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-500">85%成本</span>
              <span class="font-mono">{{ formatPrice(detail.cost_85) }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-500">获利盘</span>
              <span class="font-mono">{{ formatNumber(detail.winner_rate) }}%</span>
            </div>
          </div>
        </div>
        
        <div class="bg-white rounded-lg shadow p-4">
          <h3 class="text-sm font-medium text-gray-700 mb-3">风险信息</h3>
          <div class="space-y-2 text-sm">
            <div v-if="detail.float_risk_7d" class="text-red-600">
              ⚠️ 7日内有解禁风险
            </div>
            <div v-else class="text-green-600">
              ✅ 近期无解禁风险
            </div>
            <div v-if="detail.upcoming_float?.length" class="mt-2">
              <p class="text-gray-500 text-xs mb-1">即将解禁：</p>
              <div
                v-for="item in detail.upcoming_float"
                :key="item.float_date"
                class="text-xs text-gray-600"
              >
                {{ item.float_date }}: {{ formatNumber(item.float_ratio) }}%
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- LLM 分析 -->
      <div class="bg-white rounded-lg shadow p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-medium text-gray-700">智能分析</h3>
          <button
            @click="fetchAdvice"
            :disabled="adviceLoading"
            class="text-xs px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300"
          >
            {{ adviceLoading ? '分析中...' : '获取分析' }}
          </button>
        </div>
        
        <div v-if="adviceLoading" class="py-4 text-center text-gray-400">
          分析中...
        </div>
        
        <div v-else-if="advice" class="prose prose-sm max-w-none">
          <div
            class="p-3 rounded text-sm"
            :class="advice.analysis_mode === 'llm' ? 'bg-blue-50' : 'bg-gray-50'"
          >
            <div class="flex items-center space-x-2 mb-2">
              <span
                class="px-2 py-0.5 text-xs rounded"
                :class="advice.analysis_mode === 'llm' ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'"
              >
                {{ advice.analysis_mode === 'llm' ? 'AI 分析' : '规则建议' }}
              </span>
              <span v-if="advice.analysis_meta?.model" class="text-xs text-gray-400">
                {{ advice.analysis_meta.model }}
              </span>
            </div>
            <div class="text-gray-700 whitespace-pre-wrap">{{ advice.advice_markdown }}</div>
          </div>
        </div>
        
        <div v-else class="py-4 text-center text-gray-400 text-sm">
          点击"获取分析"查看 AI 建议
        </div>
      </div>
      
      <!-- 龙虎榜 -->
      <div v-if="detail.top_list?.length" class="bg-white rounded-lg shadow p-4">
        <h3 class="text-sm font-medium text-gray-700 mb-3">近期龙虎榜</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">日期</th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">营业部</th>
                <th class="px-3 py-2 text-right text-xs font-medium text-gray-500">净额</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr v-for="item in detail.top_list" :key="item.trade_date + item.name">
                <td class="px-3 py-2">{{ item.trade_date }}</td>
                <td class="px-3 py-2">{{ item.name }}</td>
                <td class="px-3 py-2 text-right font-mono" :class="item.net >= 0 ? 'text-up' : 'text-down'">
                  {{ item.net >= 0 ? '+' : '' }}{{ formatNumber(item.net) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    
    <!-- 埋伏池对话框 -->
    <div v-if="showAmbushDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-bold mb-4">加入埋伏池</h3>
        <div class="mb-2 text-sm text-gray-500">
          提示：系统已自动填充该股票的概念题材作为默认逻辑，您可在此基础上修改补充。
        </div>
        <textarea
          v-model="ambushLogic"
          placeholder="请输入埋伏预期逻辑..."
          class="w-full p-2 border rounded"
          rows="4"
        ></textarea>
        <div class="mt-4 flex justify-end space-x-2">
          <button @click="showAmbushDialog = false" class="px-4 py-2 bg-gray-200 rounded">
            取消
          </button>
          <button @click="addToAmbush" class="px-4 py-2 bg-emerald-500 text-white rounded">
            确认添加
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { stockApi } from '@/api'
import { ambushApi } from '@/api/ambush'
import { useWatchlistStore } from '@/stores/watchlist'
import Loading from '@/components/Loading.vue'
import Error from '@/components/Error.vue'
import { getRejectReasonLabel, getStrategyFieldLabel } from '@/constants/strategyFields'

const route = useRoute()
const router = useRouter()
const watchlistStore = useWatchlistStore()

const tsCode = computed(() => route.params.tsCode)
const isSniper = computed(() => route.query.is_sniper === 'true')
const isInWatchlist = computed(() => watchlistStore.isInWatchlist(tsCode.value))

const loading = ref(false)
const error = ref('')
const errorType = ref('unknown')
const errorDetails = ref('')
const detail = ref(null)
const kline = ref([])

const adviceLoading = ref(false)
const advice = ref(null)

// 埋伏池相关状态
const showAmbushDialog = ref(false)
const ambushLogic = ref('')

const visibleConcepts = computed(() => {
  return (detail.value?.concept_names || []).slice(0, 8)
})

const conceptOverflow = computed(() => {
  return Math.max((detail.value?.concept_names || []).length - visibleConcepts.value.length, 0)
})

const latestKline = computed(() => {
  if (!kline.value?.length) return null
  return kline.value[kline.value.length - 1]
})

const indicatorHistory = computed(() => (
  isSniper.value
    ? (detail.value?.sniper_history_7d || [])
    : (detail.value?.history_7d || [])
))

function chaosBarHeight(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric < 0) return 2
  return Math.min(Math.max((numeric / 10) * 40, 2), 40)
}

function chaosBarClass(score) {
  if (Number(score) === 15) return 'bg-emerald-500'
  if (Number(score) === 10) return 'bg-green-400'
  if (Number(score) === 5) return 'bg-yellow-400'
  return 'bg-gray-300'
}

const baseScoreItems = computed(() => {
  const latest = detail.value || {}

  if (isSniper.value) {
    return [
      {
        key: 'main_control_chaos',
        label: '主力控盘度',
        scoreValue: latest.score_chaos,
        scoreLabel: `${latest.score_chaos ?? 0} / 15`,
        ruleLabel: (latest.score_chaos || 0) >= 15 ? '高度控盘' : ((latest.score_chaos || 0) >= 10 ? '趋势稳定' : '浮筹偏多'),
        description: '量价无序度越低，盘面浮筹越少，最高 15 分',
        active: (latest.score_chaos || 0) >= 10
      },
      {
        key: 'chip_vacuum',
        label: '上方筹码真空度',
        scoreValue: latest.s_chip_vacuum_score,
        scoreLabel: `${latest.s_chip_vacuum_score ?? 0} / 10`,
        ruleLabel: (latest.s_chip_vacuum_score || 0) >= 10 ? '上方无套牢盘' : ((latest.s_chip_vacuum_score || 0) >= 7 ? '套牢盘少' : '套牢盘多'),
        description: '上方 10% 空间套牢盘越少得分越高，最高 10 分',
        active: (latest.s_chip_vacuum_score || 0) >= 7
      },
      {
        key: 'ma_state',
        label: '均线状态',
        scoreValue: latest.s_ma_state_score,
        scoreLabel: `${latest.s_ma_state_score ?? 0} / 10`,
        ruleLabel: (latest.s_ma_state_score || 0) >= 10 ? '粘合' : ((latest.s_ma_state_score || 0) >= 7 ? '多头排列' : '缠绕偏强'),
        description: '均线粘合度/多头排列加分，最高 10 分',
        active: (latest.s_ma_state_score || 0) >= 4
      },
      {
        key: 'safety_margin',
        label: '安全边际',
        scoreValue: latest.s_safety_margin_score,
        scoreLabel: `${latest.s_safety_margin_score ?? 0} / 10`,
        ruleLabel: (latest.s_safety_margin_score || 0) >= 10 ? '安全边际极高' : ((latest.s_safety_margin_score || 0) >= 6 ? '合理区间' : '偏离过大'),
        description: '股价与 20日线 乖离率合理度，最高 10 分',
        active: (latest.s_safety_margin_score || 0) >= 6
      },
      {
        key: 'macd_weekly',
        label: 'MACD周线',
        scoreValue: latest.s_macd_weekly_score,
        scoreLabel: `${latest.s_macd_weekly_score ?? 0} / 15`,
        ruleLabel: (latest.s_macd_weekly_score || 0) >= 15 ? '零轴附近金叉' : ((latest.s_macd_weekly_score || 0) >= 10 ? '红柱放大' : '零轴粘合'),
        description: '周线级别趋势与动能配合情况，最高 15 分',
        active: (latest.s_macd_weekly_score || 0) >= 5
      }
    ]
  }

  const latestKlineVal = latestKline.value || {}
  const close = latestKlineVal.close
  const ma20 = latestKlineVal.ma20
  const low = latestKlineVal.low
  const high = latestKlineVal.high
  const pctChg = detail.value?.pct_chg

  let bodyScore = 0
  if (close != null && low != null && high != null) {
    if (high > low) {
      const bodyRatio = (close - low) / (high - low)
      if (bodyRatio >= 0.7) bodyScore = 10
      else if (bodyRatio >= 0.5) bodyScore = 7
      else if (bodyRatio >= 0.3) bodyScore = 4
    } else if (high === low && pctChg != null && pctChg > 0) {
      bodyScore = 10
    }
  }

  let vrScore = 0
  const volumeRatio = detail.value?.volume_ratio
  if (volumeRatio != null) {
    if (volumeRatio >= 2.0) vrScore = 5
    else if (volumeRatio >= 1.5) vrScore = 4
    else if (volumeRatio >= 1.0) vrScore = 2
  }

  let turnoverScore = 0
  const turnoverRate = detail.value?.turnover_rate
  if (turnoverRate != null) {
    if (turnoverRate >= 3.0) turnoverScore = 5
    else if (turnoverRate >= 1.5) turnoverScore = 4
    else if (turnoverRate >= 0.5) turnoverScore = 2
  }

  let safetyScore = 0
  if (ma20 != null && ma20 > 0 && close != null) {
    const dev = close / ma20
    if (dev >= 0.95 && dev <= 1.10) safetyScore = 10
    else if (dev >= 0.90 && dev <= 1.20) safetyScore = 6
    else if (dev >= 0.85 && dev <= 1.30) safetyScore = 3
  }

  return [
    {
      key: 'trend',
      label: '趋势基线',
      scoreValue: detail.value?.trend_baseline ? 15 : 0,
      scoreLabel: `${detail.value?.trend_baseline ? 15 : 0} / 15`,
      ruleLabel: detail.value?.trend_baseline ? '收盘站上 ma60' : '未站上 ma60',
      description: '收盘价高于 ma60 记 15 分',
      active: !!detail.value?.trend_baseline
    },
    {
      key: 'chip',
      label: getStrategyFieldLabel('chip_vacuum'),
      scoreValue: null,
      scoreLabel: detail.value?.chip_vacuum ? '>=8 / 15' : '0 / 15',
      ruleLabel: detail.value?.chip_vacuum ? '命中阈值' : '未命中',
      description: '按上方筹码压力计算，命中后该项至少 8 分',
      active: !!detail.value?.chip_vacuum
    },
    {
      key: 'body',
      label: 'K线实体',
      scoreValue: bodyScore,
      scoreLabel: `${bodyScore} / 10`,
      ruleLabel: bodyScore > 0 ? '实体达标' : '实体不足',
      description: '按收盘在当日振幅中的位置计算，最高 10 分',
      active: bodyScore > 0
    },
    {
      key: 'liquidity',
      label: getStrategyFieldLabel('liquidity_base'),
      scoreValue: vrScore + turnoverScore,
      scoreLabel: `${vrScore + turnoverScore} / 10`,
      ruleLabel: `${vrScore} + ${turnoverScore}`,
      description: '量比最高 5 分，换手率最高 5 分',
      active: vrScore + turnoverScore > 0
    },
    {
      key: 'safety',
      label: '安全边际',
      scoreValue: safetyScore,
      scoreLabel: `${safetyScore} / 10`,
      ruleLabel: safetyScore > 0 ? '处于 ma20 合理区间' : '偏离过大',
      description: '收盘价与 ma20 的偏离越合理，得分越高',
      active: safetyScore > 0
    }
  ]
})

const momentumScoreItems = computed(() => {
  const latest = detail.value || {}

  if (isSniper.value) {
    return [
      {
        key: 'low_volume',
        label: '极致地量',
        scoreValue: latest.s_low_volume_score,
        scoreLabel: `${latest.s_low_volume_score ?? 0} / 8`,
        ruleLabel: (latest.s_low_volume_score || 0) >= 8 ? '地量吸筹' : ((latest.s_low_volume_score || 0) >= 4 ? '缩量调整' : '未出现缩量'),
        description: '日换手率低于 1.5% 或严重缩量，最高 8 分',
        active: (latest.s_low_volume_score || 0) >= 4
      },
      {
        key: 'golden_pit',
        label: '黄金坑/骗线',
        scoreValue: latest.s_golden_pit_score,
        scoreLabel: `${latest.s_golden_pit_score ?? 0} / 10`,
        ruleLabel: (latest.s_golden_pit_score || 0) >= 10 ? '快速收回' : '未出现',
        description: '跌破均线洗盘后，3日内反包收回，最高 10 分',
        active: (latest.s_golden_pit_score || 0) >= 10
      },
      {
        key: 'ignition',
        label: '放量点火首阳',
        scoreValue: latest.s_ignition_score,
        scoreLabel: `${latest.s_ignition_score ?? 0} / 10`,
        ruleLabel: (latest.s_ignition_score || 0) >= 10 ? '放量首阳' : ((latest.s_ignition_score || 0) >= 5 ? '试盘长上影' : '未出现'),
        description: '量比突增且日线实体饱满/长上影试盘，最高 10 分',
        active: (latest.s_ignition_score || 0) >= 5
      },
      {
        key: 'top_list_score',
        label: '龙虎榜/大宗',
        scoreValue: latest.s_top_list_score,
        scoreLabel: `${latest.s_top_list_score ?? 0} / 7`,
        ruleLabel: (latest.s_top_list_score || 0) >= 7 ? '机构主买' : ((latest.s_top_list_score || 0) >= 4 ? '资金参与' : '未上榜'),
        description: '机构主力买入或大宗交易溢价接盘，最高 7 分',
        active: (latest.s_top_list_score || 0) >= 4
      },
      {
        key: 'news_score',
        label: '消息面共振',
        scoreValue: latest.s_news_score,
        scoreLabel: `${latest.s_news_score ?? 0} / 5`,
        ruleLabel: (latest.s_news_score || 0) >= 5 ? '实质利好' : '无明显利好',
        description: '产业利好落地/研报首次覆盖加分，最高 5 分',
        active: (latest.s_news_score || 0) >= 5
      }
    ]
  }

  const winnerScore = (detail.value?.winner_rate || 0) >= 80 ? 5 : 0
  const riskPenalty = detail.value?.float_risk_7d ? -20 : 0

  return [
    {
      key: 'limit_up',
      label: '当日涨停',
      scoreValue: detail.value?.is_limit_up ? 15 : 0,
      scoreLabel: `${detail.value?.is_limit_up ? 15 : 0} / 15`,
      ruleLabel: detail.value?.is_limit_up ? '当日涨停' : '未涨停',
      description: '当日涨跌幅达到涨停标准记 15 分',
      active: !!detail.value?.is_limit_up
    },
    {
      key: 'bull',
      label: '多头趋势',
      scoreValue: detail.value?.bull_trend ? 10 : 0,
      scoreLabel: `${detail.value?.bull_trend ? 10 : 0} / 10`,
      ruleLabel: detail.value?.bull_trend ? 'ma5 > ma20 > ma60' : '未形成',
      description: '均线多头排列且收盘站上 ma5 记 10 分',
      active: !!detail.value?.bull_trend
    },
    {
      key: 'limit_up_20d',
      label: '近 20 日涨停记忆',
      scoreValue: detail.value?.limit_up_20d ? 10 : 0,
      scoreLabel: `${detail.value?.limit_up_20d ? 10 : 0} / 10`,
      ruleLabel: detail.value?.limit_up_20d ? '存在涨停' : '无涨停',
      description: '近 20 日出现过涨停记 10 分',
      active: !!detail.value?.limit_up_20d
    },
    {
      key: 'winner',
      label: '获利盘加分',
      scoreValue: winnerScore,
      scoreLabel: `${winnerScore} / 5`,
      ruleLabel: winnerScore ? '获利盘 >= 80%' : '获利盘 < 80%',
      description: '获利盘达到 80% 以上记 5 分',
      active: winnerScore > 0
    },
    {
      key: 'top_list',
      label: '龙虎榜净流入',
      scoreValue: detail.value?.top_list_3d ? 5 : 0,
      scoreLabel: `${detail.value?.top_list_3d ? 5 : 0} / 5`,
      ruleLabel: detail.value?.top_list_3d ? '近 3 日净流入' : '未触发',
      description: '近 3 日龙虎榜净流入为正记 5 分',
      active: !!detail.value?.top_list_3d
    },
    {
      key: 'risk',
      label: '解禁风险扣分',
      scoreValue: riskPenalty,
      scoreLabel: `${riskPenalty} / -20`,
      ruleLabel: detail.value?.float_risk_7d ? '7 日内有解禁' : '无解禁风险',
      description: '7 日内有解禁风险时扣 20 分',
      active: !!detail.value?.float_risk_7d,
      penalty: true
    }
  ]
})

const detailIndicators = computed(() => {
  const history = isSniper.value ? (detail.value?.sniper_history_7d || []) : (detail.value?.history_7d || [])
  const latest = detail.value || {}

  // Helpers to resolve trend of a key from history
  const getTrendList = (key, isBoolean = false) => {
    return history.map(h => isBoolean ? !!h[key] : Number(h[key] || 0) > 0)
  }

  if (isSniper.value) {
    // 15 Sniper indicators
    return [
      {
        key: 'st_risk',
        label: 'ST风险过滤',
        description: '标的被特别处理 ST/退市风险，触发直接淘汰',
        latestActive: !!latest.sniper_rejected && latest.sniper_reject_reason === 'ST',
        latestValue: (latest.sniper_rejected && latest.sniper_reject_reason === 'ST') ? 'ST股 (直接过滤)' : '通过',
        trend: history.map(h => !!h.sniper_rejected && h.sniper_reject_reason === 'ST'),
        isPenalty: true,
      },
      {
        key: 'ma_break',
        label: '均线加速破位',
        description: '均线死叉向下且加速发散，触发直接淘汰',
        latestActive: !!latest.sniper_rejected && latest.sniper_reject_reason === 'MA_BREAK',
        latestValue: (latest.sniper_rejected && latest.sniper_reject_reason === 'MA_BREAK') ? '破位 (直接过滤)' : '通过',
        trend: history.map(h => !!h.sniper_rejected && h.sniper_reject_reason === 'MA_BREAK'),
        isPenalty: true,
      },
      {
        key: 'weekly_macd_dead',
        label: '周线MACD死叉',
        description: 'MACD周线高位死叉且绿柱放大，触发直接淘汰',
        latestActive: !!latest.sniper_rejected && latest.sniper_reject_reason === 'WEEKLY_MACD_DEAD',
        latestValue: (latest.sniper_rejected && latest.sniper_reject_reason === 'WEEKLY_MACD_DEAD') ? '死叉 (直接过滤)' : '通过',
        trend: history.map(h => !!h.sniper_rejected && h.sniper_reject_reason === 'WEEKLY_MACD_DEAD'),
        isPenalty: true,
      },
      {
        key: 'holder_surge',
        label: '无序度过高',
        description: '量价无序度达到 8 或以上，触发 HOLDER_SURGE 直接淘汰',
        latestActive: !!latest.sniper_rejected && latest.sniper_reject_reason === 'HOLDER_SURGE',
        latestValue: (latest.sniper_rejected && latest.sniper_reject_reason === 'HOLDER_SURGE') ? '无序 (直接过滤)' : '通过',
        trend: history.map(h => !!h.sniper_rejected && h.sniper_reject_reason === 'HOLDER_SURGE'),
        isPenalty: true,
      },
      {
        key: 'fundamental_warning',
        label: '突发基本面恶化',
        description: '突发基本面恶化（大额减持/立案调查等），直接淘汰',
        latestActive: !!latest.sniper_rejected && latest.sniper_reject_reason === 'FUNDAMENTAL_WARN',
        latestValue: (latest.sniper_rejected && latest.sniper_reject_reason === 'FUNDAMENTAL_WARN') ? '恶化 (直接过滤)' : '通过',
        trend: history.map(h => !!h.sniper_rejected && h.sniper_reject_reason === 'FUNDAMENTAL_WARN'),
        isPenalty: true,
      },
      {
        key: 'main_control_chaos',
        label: '主力控盘度 (量价无序度)',
        description: '结合日级量价无序度综合判定，无序度越低，盘面浮筹越少。',
        latestActive: (latest.score_chaos || 0) >= 10,
        latestValue: latest.chaos_index_val != null ? `${latest.chaos_index_val} / ${latest.score_chaos || 0}分` : '数据不足',
        trend: history.map(h => ({ value: h.chaos_index_val, score: h.score_chaos || 0 })),
        isChaos: true,
      },
      {
        key: 'chip_vacuum',
        label: '上方筹码真空度',
        description: '当前价上方 10% 区间内套牢盘比例',
        latestActive: (latest.s_chip_vacuum_score || 0) >= 7,
        latestValue: latest.s_chip_vacuum_score != null ? `${latest.s_chip_vacuum_score}分` : '-',
        trend: history.map(h => (h.s_chip_vacuum_score || 0) >= 7),
      },
      {
        key: 'ma_state',
        label: '均线状态',
        description: '5/10/20/60日均线粘合度与排列状态',
        latestActive: (latest.s_ma_state_score || 0) >= 7,
        latestValue: latest.s_ma_state_score != null ? `${latest.s_ma_state_score}分` : '-',
        trend: history.map(h => (h.s_ma_state_score || 0) >= 7),
      },
      {
        key: 'safety_margin',
        label: '安全边际',
        description: '股价与20日均线的偏离度合理性',
        latestActive: (latest.s_safety_margin_score || 0) >= 6,
        latestValue: latest.s_safety_margin_score != null ? `${latest.s_safety_margin_score}分` : '-',
        trend: history.map(h => (h.s_safety_margin_score || 0) >= 6),
      },
      {
        key: 'macd_weekly_score',
        label: 'MACD周线评分',
        description: '周线 MACD 处于零轴附近金叉或红柱放大',
        latestActive: (latest.s_macd_weekly_score || 0) >= 10,
        latestValue: latest.s_macd_weekly_score != null ? `${latest.s_macd_weekly_score}分` : '-',
        trend: history.map(h => (h.s_macd_weekly_score || 0) >= 10),
      },
      {
        key: 'low_volume',
        label: '极致地量',
        description: '换手率低于1.5%或成交量严重缩水',
        latestActive: (latest.s_low_volume_score || 0) >= 4,
        latestValue: latest.s_low_volume_score != null ? `${latest.s_low_volume_score}分` : '-',
        trend: history.map(h => (h.s_low_volume_score || 0) >= 4),
      },
      {
        key: 'golden_pit',
        label: '黄金坑/骗线',
        description: '跌破支撑后放量快速反包收回',
        latestActive: (latest.s_golden_pit_score || 0) >= 10,
        latestValue: latest.s_golden_pit_score != null ? `${latest.s_golden_pit_score}分` : '-',
        trend: history.map(h => (h.s_golden_pit_score || 0) >= 10),
      },
      {
        key: 'ignition',
        label: '放量点火首阳',
        description: '成交量异常放大且日线实体阳线饱满',
        latestActive: (latest.s_ignition_score || 0) >= 10,
        latestValue: latest.s_ignition_score != null ? `${latest.s_ignition_score}分` : '-',
        trend: history.map(h => (h.s_ignition_score || 0) >= 10),
      },
      {
        key: 'top_list_score',
        label: '龙虎榜/大宗',
        description: '机构主力大额净买入或大宗溢价接盘',
        latestActive: (latest.s_top_list_score || 0) >= 4,
        latestValue: latest.s_top_list_score != null ? `${latest.s_top_list_score}分` : '-',
        trend: history.map(h => (h.s_top_list_score || 0) >= 4),
      },
      {
        key: 'news_score',
        label: '消息面共振',
        description: '核心基本面利好或分析师强力推荐',
        latestActive: (latest.s_news_score || 0) >= 5,
        latestValue: latest.s_news_score != null ? `${latest.s_news_score}分` : '-',
        trend: history.map(h => (h.s_news_score || 0) >= 5),
      }
    ]
  }

  // 15 indicators
  return [
    {
      key: 'trend_baseline',
      label: '趋势基线',
      description: '收盘价高于 60日均线 ma60',
      latestActive: !!latest.trend_baseline,
      latestValue: latest.trend_baseline ? '达成 (15分)' : '未达成',
      trend: getTrendList('trend_baseline'),
    },
    {
      key: 'chip_vacuum',
      label: '筹码真空',
      description: '上方 9.5% 价格区间内筹码分布小于 10%',
      latestActive: !!latest.chip_vacuum,
      latestValue: latest.chip_vacuum ? '达成' : '未达成',
      trend: getTrendList('chip_vacuum'),
    },
    {
      key: 'kline_body',
      label: 'K线实体',
      description: '收盘价处于当日最高与最低价振幅的相对高位',
      latestActive: !!latest.kline_body,
      latestValue: latest.kline_body ? '达成' : '未达成',
      trend: getTrendList('kline_body'),
    },
    {
      key: 'liquidity_base',
      label: '量能活跃',
      description: '量比 ≥ 1.8 且换手率 ≥ 2%',
      latestActive: !!latest.liquidity_base,
      latestValue: latest.liquidity_base ? '达成' : '未达成',
      trend: getTrendList('liquidity_base'),
    },
    {
      key: 'safety_margin',
      label: '安全边际',
      description: '收盘价偏离 20日均线 ma20 幅度小于 25%',
      latestActive: !!latest.safety_margin,
      latestValue: latest.safety_margin ? '达成' : '未达成',
      trend: getTrendList('safety_margin'),
    },
    {
      key: 'is_limit_up',
      label: '当日涨停',
      description: '当日价格达到涨停板标准 (+15分)',
      latestActive: !!latest.is_limit_up,
      latestValue: latest.is_limit_up ? '涨停 (+15分)' : '否',
      trend: getTrendList('is_limit_up'),
    },
    {
      key: 'bull_trend',
      label: '多头排列',
      description: '均线呈 ma5 > ma20 > ma60 多头排列 (+10分)',
      latestActive: !!latest.bull_trend,
      latestValue: latest.bull_trend ? '多头 (+10分)' : '否',
      trend: getTrendList('bull_trend'),
    },
    {
      key: 'limit_up_20d',
      label: '近20日涨停记忆',
      description: '过去 20 个交易日内出现过涨停记录 (+10分)',
      latestActive: !!latest.limit_up_20d,
      latestValue: latest.limit_up_20d ? '有记忆 (+10分)' : '无',
      trend: getTrendList('limit_up_20d'),
    },
    {
      key: 'winner_rate_80',
      label: '获利盘优势',
      description: '最新收盘获利盘比例达到 80% 以上 (+5分)',
      latestActive: (latest.winner_rate || 0) >= 80,
      latestValue: (latest.winner_rate || 0) >= 80 ? '优势 (+5分)' : '普通',
      trend: history.map(h => (h.winner_rate || 0) >= 80),
    },
    {
      key: 'top_list_3d',
      label: '龙虎榜加分',
      description: '近 3 日龙虎榜资金呈净流入状态 (+5分)',
      latestActive: !!latest.top_list_3d,
      latestValue: latest.top_list_3d ? '净流入 (+5分)' : '否',
      trend: getTrendList('top_list_3d'),
    },
    {
      key: 'float_risk_7d',
      label: '解禁风险扣分',
      description: '未来 7 个交易日内存在解禁风险 (-20分)',
      latestActive: !!latest.float_risk_7d,
      latestValue: latest.float_risk_7d ? '有风险 (-20分)' : '无',
      trend: getTrendList('float_risk_7d'),
      isPenalty: true,
    },
    {
      key: 'st_risk',
      label: 'ST风险过滤',
      description: '标的被特别处理 ST/退市风险，触发直接淘汰',
      latestActive: !!latest.st_risk,
      latestValue: latest.st_risk ? 'ST股 (直接过滤)' : '非ST',
      trend: getTrendList('st_risk'),
      isPenalty: true,
    },
    {
      key: 'debt_to_assets_limit',
      label: '资产负债率',
      description: '最新财务资产负债率不得高于 85%',
      latestActive: (latest.fin_indicator?.debt_to_assets || 0) > 85,
      latestValue: (latest.fin_indicator?.debt_to_assets || 0) > 85 ? '过高 (过滤)' : '正常',
      trend: history.map(() => (latest.fin_indicator?.debt_to_assets || 0) > 85),
      isPenalty: true,
    },
    {
      key: 'roe_limit',
      label: 'ROE盈利限制',
      description: '最新扣非 ROE 不得低于 1.5%',
      latestActive: (latest.fin_indicator?.roe || 0) < 1.5 && (latest.fin_indicator?.roe !== null),
      latestValue: ((latest.fin_indicator?.roe || 0) < 1.5 && (latest.fin_indicator?.roe !== null)) ? '过低 (过滤)' : '正常',
      trend: history.map(() => ((latest.fin_indicator?.roe || 0) < 1.5 && (latest.fin_indicator?.roe !== null))),
      isPenalty: true,
    },
    {
      key: 'final_score_rule',
      label: '综合评分及格',
      description: '计算得到的综合最终分不得低于 50分',
      latestActive: (latest.final_score || 0) < 50,
      latestValue: (latest.final_score || 0) < 50 ? '不及格' : '及格',
      trend: history.map(h => (h.final_score || 0) < 50),
      isPenalty: true,
    }
  ]
})

const baseScoreSummary = computed(() => {
  return baseScoreItems.value
    .map(item => item.scoreValue)
    .filter(score => score != null)
    .reduce((sum, score) => sum + Number(score || 0), 0)
})

const momentumScoreSummary = computed(() => {
  return momentumScoreItems.value
    .filter(item => !item.penalty)
    .map(item => item.scoreValue)
    .reduce((sum, score) => sum + Number(score || 0), 0)
})

const penaltyScoreSummary = computed(() => {
  const penalty = momentumScoreItems.value
    .filter(item => item.penalty)
    .map(item => item.scoreValue)
    .reduce((sum, score) => sum + Number(score || 0), 0)
  return penalty < 0 ? `${penalty}` : `+${penalty}`
})

const chipScoreSummary = computed(() => {
  if (!detail.value?.chip_vacuum) return ''
  return '，另含筹码真空内部计分'
})

const activeBaseLabels = computed(() => {
  return baseScoreItems.value
    .filter(item => item.active)
    .map(item => item.label)
})

const activeMomentumLabels = computed(() => {
  return momentumScoreItems.value
    .filter(item => item.active && !item.penalty)
    .map(item => item.label)
})

const inactiveKeyLabels = computed(() => {
  return [
    ...baseScoreItems.value.filter(item => !item.active).map(item => item.label),
    ...momentumScoreItems.value.filter(item => !item.active && !item.penalty).map(item => item.label)
  ]
})

const summaryToneClass = computed(() => {
  if (detail.value?.rejected) {
    return 'border-amber-200 bg-amber-50 text-amber-900'
  }
  if ((detail.value?.final_score || 0) >= 95) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  }
  return 'border-blue-200 bg-blue-50 text-blue-900'
})

const summaryBadgeClass = computed(() => {
  return detail.value?.rejected
    ? 'bg-amber-100 text-amber-700'
    : 'bg-emerald-100 text-emerald-700'
})

const scoreSummaryText = computed(() => {
  const score = detail.value?.final_score ?? 0
  const strengths = [...activeBaseLabels.value, ...activeMomentumLabels.value].slice(0, 3)
  const weaknesses = inactiveKeyLabels.value.slice(0, 3)
  const rejectReason = detail.value?.reject_reason ? `，未通过项：${getRejectShort(detail.value.reject_reason)}` : ''
  const riskText = detail.value?.float_risk_7d ? '，且存在 7 日内解禁风险' : ''

  const strengthText = strengths.length ? `当前主要得分来自 ${strengths.join('、')}` : '当前暂无明显加分项'
  const weaknessText = weaknesses.length ? `，短板集中在 ${weaknesses.join('、')}` : ''

  if (detail.value?.rejected) {
    return `当前总分 ${score} 分，${strengthText}${weaknessText}${rejectReason}${riskText}。`
  }

  return `当前总分 ${score} 分，${strengthText}${weaknessText}${riskText}。`
})

// K线表格数据（倒序，最新的在前面，最多显示10条）
const klineTableData = computed(() => {
  if (!kline.value || kline.value.length === 0) return []
  const data = [...kline.value].reverse().slice(0, 10)
  return data.map((item, index) => {
    // 计算涨跌额 = 收盘 - 前一收盘
    let change = null
    if (index < data.length - 1) {
      const prevClose = data[index + 1].close
      if (prevClose != null && item.close != null) {
        change = item.close - prevClose
      }
    }
    return {
      ...item,
      change
    }
  })
})

function toggleWatchlist() {
  if (isInWatchlist.value) {
    watchlistStore.remove(tsCode.value)
  } else {
    watchlistStore.add({
      tsCode: tsCode.value,
      name: detail.value?.name || tsCode.value,
      industry: detail.value?.industry || '',
      conceptNames: detail.value?.concept_names || [],
      conceptText: detail.value?.concept_text || ''
    })
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
  return `${sign}${val.toFixed(2)}%`
}

function formatNumber(val) {
  if (val == null) return '-'
  return val.toFixed(2)
}

function formatFlag(val) {
  if (val == null) return '-'
  return Number(val) === 1 ? '是' : '否'
}

function formatPrice(val) {
  if (val == null) return '-'
  return val.toFixed(2)
}

function formatChange(val) {
  if (val == null) return '-'
  const sign = val > 0 ? '+' : ''
  return `${sign}${val.toFixed(2)}`
}

function formatVol(val) {
  // vol是股数，转为万手（1万手 = 10000 * 100 = 1000000股）
  if (val == null) return '-'
  return (val / 1000000).toFixed(2)
}

function formatAmount(val) {
  // amount是元，转为亿
  if (val == null) return '-'
  return (val / 100000000).toFixed(2)
}

function getRejectShort(reason) {
  return getRejectReasonLabel(reason)
}

async function fetchData() {
  loading.value = true
  error.value = ''
  errorType.value = 'unknown'
  errorDetails.value = ''
  
  try {
    const params = isSniper.value ? { is_sniper: true } : {}
    const [detailData, klineData] = await Promise.all([
      stockApi.getDetail(tsCode.value, params),
      stockApi.getKline(tsCode.value, 60)
    ])
    detail.value = detailData
    kline.value = klineData || []
  } catch (err) {
    error.value = err.message
    errorType.value = err.type || 'unknown'
    errorDetails.value = err.original?.message || ''
  } finally {
    loading.value = false
  }
}

async function switchIndicator(indicator) {
  const nextIsSniper = indicator === 'sniper'
  if (nextIsSniper === isSniper.value || loading.value) return

  const query = { ...route.query }
  if (nextIsSniper) {
    query.is_sniper = 'true'
  } else {
    delete query.is_sniper
  }

  await router.replace({ query })
  advice.value = null
  await fetchData()
}

async function fetchAdvice() {
  adviceLoading.value = true
  
  try {
    const data = await stockApi.getAdvice(tsCode.value)
    advice.value = data
  } catch (err) {
    console.error('获取分析失败:', err)
  } finally {
    adviceLoading.value = false
  }
}

function goToReview() {
  router.push({
    path: '/review',
    query: {
      tsCode: tsCode.value,
      name: detail.value?.name || tsCode.value
    }
  })
}

// 打开对话框时自动填充概念题材
function openAmbushDialog() {
  showAmbushDialog.value = true
  
  // 如果已有内容，不覆盖
  if (ambushLogic.value.trim()) {
    return
  }
  
  // 尝试从详情数据中获取概念题材作为默认值
  const conceptText = detail.value?.concept_text || ''
  if (conceptText) {
    ambushLogic.value = `概念题材：${conceptText}`
  }
}

async function addToAmbush() {
  // 必填非空校验
  if (!ambushLogic.value.trim()) {
    alert('请输入埋伏预期逻辑')
    return
  }
  
  try {
    await ambushApi.addToAmbushPool(tsCode.value, ambushLogic.value)
    showAmbushDialog.value = false
    ambushLogic.value = ''
    alert('添加成功')
  } catch (err) {
    alert(`添加失败: ${err.message}`)
  }
}

onMounted(fetchData)
</script>
