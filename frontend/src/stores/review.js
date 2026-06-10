import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { hydratePersistentList, readLocalList, savePersistentList } from '@/utils/persistentStore'

// 复盘记录存储（桌面文件 + localStorage 兜底）
export const useReviewStore = defineStore('review', () => {
  const STORAGE_KEY = 'stocknew_reviews'
  
  const list = ref(readLocalList(STORAGE_KEY))
  hydrate()
  
  const count = computed(() => list.value.length)
  
  // 检查某只股票是否已有复盘记录
  const hasReview = computed(() => (tsCode) => {
    return list.value.some(item => item.tsCode === tsCode && !item.isReviewed)
  })
  
  // 获取某只股票的复盘记录
  const getReviewByCode = computed(() => (tsCode) => {
    return list.value.filter(item => item.tsCode === tsCode)
  })
  
  // 添加复盘记录
  function add(data) {
    const review = {
      id: generateId(),
      tsCode: data.tsCode,
      name: data.name,
      industry: data.industry || '',
      conceptNames: Array.isArray(data.conceptNames) ? data.conceptNames : [],
      conceptText: data.conceptText || '',
      isWatching: data.isWatching ?? true,
      planBuy: data.planBuy ?? false,
      judgment: data.judgment || '',
      // 当时的策略信号
      strategyScore: data.strategyScore,
      pctChg: data.pctChg,
      turnoverRate: data.turnoverRate,
      volumeRatio: data.volumeRatio,
      // 复盘状态
      isReviewed: false,
      reviewConclusion: '',
      reviewedAt: null,
      // 时间戳
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    }
    
    list.value.unshift(review)
    save()
    return review
  }
  
  // 更新复盘记录
  function update(id, data) {
    const index = list.value.findIndex(item => item.id === id)
    if (index === -1) return null
    
    list.value[index] = {
      ...list.value[index],
      ...data,
      updatedAt: new Date().toISOString()
    }
    save()
    return list.value[index]
  }
  
  // 删除复盘记录
  function remove(id) {
    const index = list.value.findIndex(item => item.id === id)
    if (index === -1) return false
    
    list.value.splice(index, 1)
    save()
    return true
  }
  
  async function hydrate() {
    list.value = await hydratePersistentList(STORAGE_KEY)
  }

  function save() {
    savePersistentList(STORAGE_KEY, list.value)
  }
  
  // 生成唯一ID
  function generateId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  }
  
  // 导出数据（用于备份）
  function exportData() {
    return JSON.stringify(list.value, null, 2)
  }
  
  // 导入数据
  function importData(jsonStr) {
    try {
      const data = JSON.parse(jsonStr)
      if (Array.isArray(data)) {
        list.value = data
        save()
        return true
      }
      return false
    } catch (err) {
      console.error('导入复盘数据失败:', err)
      return false
    }
  }
  
  return {
    list,
    count,
    hasReview,
    getReviewByCode,
    add,
    update,
    remove,
    exportData,
    importData
  }
})
