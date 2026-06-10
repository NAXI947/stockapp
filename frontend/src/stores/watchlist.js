import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { hydratePersistentList, readLocalList, savePersistentList } from '@/utils/persistentStore'

// 自选股存储（桌面文件 + localStorage 兜底）
export const useWatchlistStore = defineStore('watchlist', () => {
  const STORAGE_KEY = 'stocknew_watchlist'
  
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
    remove
  }
})
