<template>
  <div class="flex items-center justify-center py-12">
    <div class="text-center max-w-md px-4">
      <!-- 错误图标 -->
      <div class="text-4xl mb-3">{{ icon }}</div>
      
      <!-- 错误标题 -->
      <h3 class="text-lg font-medium text-gray-900 mb-2">{{ displayTitle }}</h3>
      
      <!-- 错误详情 -->
      <p class="text-sm text-gray-500 mb-2">{{ displayMessage }}</p>
      
      <!-- 技术详情（开发模式显示） -->
      <p v-if="showDetails && details" class="text-xs text-gray-400 mb-4 bg-gray-50 p-2 rounded">
        {{ details }}
      </p>
      
      <!-- 操作按钮 -->
      <div class="flex items-center justify-center space-x-3">
        <button
          v-if="showRetry && type !== 'auth'"
          @click="$emit('retry')"
          class="px-4 py-2 bg-blue-500 text-white text-sm rounded-md hover:bg-blue-600 transition-colors"
        >
          {{ retryText }}
        </button>
        <button
          v-if="type === 'auth'"
          @click="goToLogin"
          class="px-4 py-2 bg-blue-500 text-white text-sm rounded-md hover:bg-blue-600 transition-colors"
        >
          重新登录
        </button>
        <button
          v-if="showBack"
          @click="goBack"
          class="px-4 py-2 border border-gray-300 text-gray-700 text-sm rounded-md hover:bg-gray-50 transition-colors"
        >
          返回
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  // 错误类型: network, auth, server, notfound, timeout, unknown
  type: {
    type: String,
    default: 'unknown'
  },
  title: {
    type: String,
    default: ''
  },
  message: {
    type: String,
    default: ''
  },
  details: {
    type: String,
    default: ''
  },
  showRetry: {
    type: Boolean,
    default: true
  },
  showBack: {
    type: Boolean,
    default: false
  },
  showDetails: {
    type: Boolean,
    default: false
  },
  retryText: {
    type: String,
    default: '重试'
  }
})

defineEmits(['retry'])

const router = useRouter()

// 根据错误类型显示不同图标
const icon = computed(() => {
  const icons = {
    network: '🌐',
    auth: '🔒',
    server: '🔧',
    notfound: '🔍',
    timeout: '⏱️',
    unknown: '⚠️'
  }
  return icons[props.type] || icons.unknown
})

// 根据错误类型显示不同标题
const displayTitle = computed(() => {
  if (props.title) return props.title
  
  const titles = {
    network: '网络连接失败',
    auth: '登录已过期',
    server: '服务器错误',
    notfound: '资源不存在',
    timeout: '请求超时',
    unknown: '出错了'
  }
  return titles[props.type] || titles.unknown
})

// 根据错误类型显示不同消息
const displayMessage = computed(() => {
  if (props.message) return props.message
  
  const messages = {
    network: '请检查网络连接后重试',
    auth: '您的登录已过期，请重新登录',
    server: '服务器暂时不可用，请稍后重试',
    notfound: '请求的资源不存在或已被删除',
    timeout: '请求响应时间过长，请稍后重试',
    unknown: '请求失败，请稍后重试'
  }
  return messages[props.type] || messages.unknown
})

function goToLogin() {
  localStorage.removeItem('api_token')
  router.push('/login')
}

function goBack() {
  router.back()
}
</script>
