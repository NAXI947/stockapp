import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 简单内存缓存
const cache = new Map()

// 缓存配置（单位：毫秒）
const CACHE_DURATION = {
  picks: 60 * 1000,        // 选股数据 1 分钟
  detail: 30 * 1000,       // 个股详情 30 秒
  kline: 5 * 60 * 1000,    // K线 5 分钟
  advice: 10 * 60 * 1000,  // AI建议 10 分钟
  default: 60 * 1000       // 默认 1 分钟
}

// 请求去重（用于防止重复请求）
const pendingRequests = new Map()

// 生成缓存 key
function getCacheKey(config) {
  return `${config.method}:${config.url}:${JSON.stringify(config.params || {})}`
}

// 生成请求 key（用于去重）
function getRequestKey(config) {
  return `${config.method}:${config.url}:${JSON.stringify(config.params || {})}:${JSON.stringify(config.data || {})}`
}

// 请求拦截器 - 添加 token 和缓存处理
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('api_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    
    // 检查缓存（仅 GET 请求）
    if (config.method?.toLowerCase() === 'get' && config.cache !== false) {
      const cacheKey = getCacheKey(config)
      const cached = cache.get(cacheKey)
      
      if (cached && Date.now() - cached.time < cached.duration) {
        // 返回缓存数据，取消请求
        config.adapter = () => Promise.resolve({
          data: { code: 200, data: cached.data },
          status: 200,
          statusText: 'OK',
          headers: {},
          config
        })
      }
    }
    
    // 请求去重处理
    if (config.dedup !== false) {
      const requestKey = getRequestKey(config)
      if (pendingRequests.has(requestKey)) {
        // 返回正在进行的相同请求
        config.adapter = () => pendingRequests.get(requestKey)
      } else {
        // 记录请求
        const promise = new Promise((resolve, reject) => {
          config._resolve = resolve
          config._reject = reject
        })
        pendingRequests.set(requestKey, promise)
        config._requestKey = requestKey
      }
    }
    
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 统一错误处理和缓存
api.interceptors.response.use(
  (response) => {
    const config = response.config
    
    // 清理请求去重记录
    if (config._requestKey) {
      pendingRequests.delete(config._requestKey)
    }
    
    const data = response.data
    
    if (data.code !== 200) {
      throw new Error(data.msg || '请求失败')
    }
    
    // 缓存成功的 GET 请求
    if (config.method?.toLowerCase() === 'get' && config.cache !== false) {
      const cacheKey = getCacheKey(config)
      const url = config.url || ''
      
      // 根据 URL 确定缓存时间
      let duration = CACHE_DURATION.default
      if (url.includes('/picks')) duration = CACHE_DURATION.picks
      else if (url.includes('/detail/')) duration = CACHE_DURATION.detail
      else if (url.includes('/kline/')) duration = CACHE_DURATION.kline
      else if (url.includes('/advice')) duration = CACHE_DURATION.advice
      
      cache.set(cacheKey, {
        data: data.data,
        time: Date.now(),
        duration
      })
    }
    
    return data.data
  },
  (error) => {
    // 清理请求去重记录
    if (error.config?._requestKey) {
      pendingRequests.delete(error.config._requestKey)
    }
    
    // 错误分类
    let errorType = 'unknown'
    let errorMessage = error.message || '请求失败'
    
    if (!error.response) {
      // 无响应 - 网络错误或超时
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorType = 'timeout'
        errorMessage = '请求超时，请稍后重试'
      } else {
        errorType = 'network'
        errorMessage = '网络连接失败，请检查网络'
      }
    } else {
      const status = error.response.status
      const msg = error.response.data?.msg
      
      switch (status) {
        case 401:
          errorType = 'auth'
          errorMessage = msg || '登录已过期，请重新登录'
          localStorage.removeItem('api_token')
          break
        case 403:
          errorType = 'auth'
          errorMessage = msg || '没有权限访问'
          break
        case 404:
          errorType = 'notfound'
          errorMessage = msg || '请求的资源不存在'
          break
        case 500:
        case 502:
        case 503:
        case 504:
          errorType = 'server'
          errorMessage = msg || '服务器暂时不可用'
          break
        case 429:
          errorType = 'timeout'
          errorMessage = msg || '请求过于频繁，请稍后重试'
          break
        default:
          errorMessage = msg || `请求失败 (${status})`
      }
    }
    
    // 创建增强的错误对象
    const enhancedError = new Error(errorMessage)
    enhancedError.type = errorType
    enhancedError.original = error
    enhancedError.status = error.response?.status
    
    return Promise.reject(enhancedError)
  }
)

// 缓存清理工具
export const cacheUtils = {
  // 清理所有缓存
  clear() {
    cache.clear()
  },
  
  // 清理指定 URL 的缓存
  clearUrl(url) {
    for (const key of cache.keys()) {
      if (key.includes(url)) {
        cache.delete(key)
      }
    }
  },
  
  // 获取缓存统计
  stats() {
    return {
      size: cache.size,
      keys: Array.from(cache.keys())
    }
  }
}

// API 接口定义
export const picksApi = {
  // 获取选股结果（支持 date / is_ambush 等查询参数）
  getPicks(paramsOrDate = {}, options = {}) {
    const params = typeof paramsOrDate === 'string'
      ? { date: paramsOrDate }
      : { ...paramsOrDate }
    return api.get('/picks', { params, ...options })
  },
  
  // 强制刷新选股数据（跳过缓存）
  refreshPicks(paramsOrDate = {}) {
    this.clearCache()
    return this.getPicks(paramsOrDate, { cache: false, dedup: false })
  },
  
  // 清理选股缓存
  clearCache() {
    cacheUtils.clearUrl('/picks')
  }
}

export const stockApi = {
  // 获取 K 线数据
  getKline(tsCode, limit = 60, options = {}) {
    return api.get(`/kline/${tsCode}`, { params: { limit }, ...options })
  },
  
  // 获取个股详情
  getDetail(tsCode, date, options = {}) {
    const params = date ? { date } : {}
    return api.get(`/detail/${tsCode}`, { params, ...options })
  },
  
  // 获取股票建议（强制刷新用 cache: false）
  getAdvice(symbol, market = 'CN', options = {}) {
    return api.post('/analysis/stock_advice', { symbol, market }, options)
  },

  // 批量搜索股票
  batchSearch(queries, options = {}) {
    return api.post('/stocks/batch-search', { queries }, options)
  }
}

export const jobApi = {
  getDefinitions(options = {}) {
    return api.get('/jobs/definitions', { cache: false, ...options })
  },

  runJob(jobName, options = {}) {
    cacheUtils.clear()
    return api.post(`/jobs/${jobName}/run`, {}, { dedup: false, ...options })
  },

  runDailyDate(tradeDate, options = {}) {
    cacheUtils.clear()
    return api.post('/jobs/daily-date/run', { trade_date: tradeDate }, { dedup: false, ...options })
  },

  getTasks(options = {}) {
    return api.get('/jobs/tasks', { cache: false, dedup: false, ...options })
  },

  // 获取任务日志摘要
  getLogsSummary(days = 7, limit = 10, options = {}) {
    return api.get('/job/logs/summary', { params: { days, limit }, ...options })
  },
  
  // 获取任务阶段日志
  getStages(params = {}, options = {}) {
    return api.get('/job/stages', { params, ...options })
  }
}

export const configApi = {
  // 获取运行参数
  getRuntimeConfig(options = {}) {
    return api.get('/runtime-config', options)
  },
  
  // 更新运行参数
  updateRuntimeConfig(config, options = {}) {
    return api.put('/runtime-config', config, options)
  },

  getTushareToken(options = {}) {
    return api.get('/tushare-token', { cache: false, ...options })
  },

  updateTushareToken(token, options = {}) {
    return api.put('/tushare-token', { token }, options)
  }
}

export const dataApi = {
  getHealth(options = {}) {
    return api.get('/data-health', { cache: false, ...options })
  }
}

export { ambushApi } from './ambush'

export default api
