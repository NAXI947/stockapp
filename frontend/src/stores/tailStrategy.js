import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { hydratePersistentList, readLocalList, savePersistentList } from '@/utils/persistentStore'

// 尾盘策略选股存储（桌面文件 + localStorage 兜底）
export const useTailStrategyStore = defineStore('tailStrategy', () => {
  const STORAGE_KEY = 'stocknew_tail_strategy'
  
  const list = ref(readLocalList(STORAGE_KEY))
  hydrate()
  
  const count = computed(() => list.value.length)
  
  const isInWatchlist = computed(() => (tsCode) => {
    return list.value.some(item => item.tsCode === tsCode)
  })

  function normalizeStock(stock) {
    const tsCode = stock?.tsCode || stock?.ts_code || ''
    const conceptNames = Array.isArray(stock?.conceptNames)
      ? stock.conceptNames
      : Array.isArray(stock?.concept_names)
        ? stock.concept_names
        : []
    const conceptText = stock?.conceptText || stock?.concept_text || conceptNames.join(' / ')
    return {
      tsCode,
      name: stock?.name || tsCode,
      industry: stock?.industry || '',
      conceptNames,
      conceptText,
      // ---- 数据来自上传的EXCEL里 ----
      today_pct: stock?.today_pct || null,
      volume_ratio: stock?.volume_ratio || null,
      turnover_rate_excel: stock?.turnover_rate || null,
      amplitude: stock?.amplitude || null,
      main_net_inflow: stock?.main_net_inflow || null,
      realtime_winner_rate: stock?.realtime_winner_rate || null,
      realtime_top_list: stock?.realtime_top_list || null,
      addedAt: stock?.addedAt || new Date().toISOString()
    }
  }
  
  // 添加自选股
  function add(stock) {
    const normalized = normalizeStock(stock)
    if (!normalized.tsCode) {
      return
    }

    if (!isInWatchlist.value(normalized.tsCode)) {
      list.value.push(normalized)
      save()
    }
  }

  // 批量替换当前所有股票（或添加到现有列表），视需求而定。由于需求是"根据文件里的B列代码添加股票到尾盘策略选股"
  function addBatch(stocks) {
    stocks.forEach(stock => {
      const normalized = normalizeStock(stock)
      if (normalized.tsCode && !isInWatchlist.value(normalized.tsCode)) {
        list.value.push(normalized)
      } else if (normalized.tsCode) {
        // 如果已经存在，更新来自excel的字段
        const idx = list.value.findIndex(item => item.tsCode === normalized.tsCode)
        if (idx !== -1) {
          list.value[idx] = { ...list.value[idx], ...normalized }
        }
      }
    })
    save()
  }
  
  // 移除自选股
  function remove(tsCode) {
    list.value = list.value.filter(item => item.tsCode !== tsCode)
    save()
  }
  
  async function hydrate() {
    list.value = await hydratePersistentList(STORAGE_KEY)
  }

  function save() {
    savePersistentList(STORAGE_KEY, list.value)
  }
  
  return {
    list,
    count,
    isInWatchlist,
    add,
    addBatch,
    remove
  }
})
