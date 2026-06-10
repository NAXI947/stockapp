import api, { cacheUtils } from './index'

function clearPicksCache() {
  cacheUtils.clearUrl('/picks')
}

export const ambushApi = {
  // 添加到埋伏池
  addToAmbushPool(tsCode, expectedLogic, options = {}) {
    clearPicksCache()
    return api.post('/ambush', { 
      ts_code: tsCode, 
      expected_logic: expectedLogic 
    }, { dedup: false, ...options }).finally(clearPicksCache)
  },
  
  // 更新埋伏池
  updateAmbushPool(tsCode, data, options = {}) {
    clearPicksCache()
    return api.put(`/ambush/${tsCode}`, data, { dedup: false, ...options }).finally(clearPicksCache)
  },
  
  // 从埋伏池移除（设置状态为-1）
  removeFromAmbushPool(tsCode, options = {}) {
    return this.updateAmbushPool(tsCode, { status: -1 }, options)
  }
}
