<template>
  <div class="min-h-screen bg-bg-secondary flex items-center justify-center px-4">
    <div class="max-w-sm w-full">
      <div class="bg-white rounded-lg shadow-md p-6">
        <h2 class="text-xl font-bold text-center text-gray-900 mb-6">
          Stocknew 登录
        </h2>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              API Token
            </label>
            <input
              v-model="token"
              type="password"
              placeholder="请输入 API Token"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              @keyup.enter="handleLogin"
            />
          </div>
          
          <button
            @click="handleLogin"
            :disabled="loading || !token"
            class="w-full py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {{ loading ? '登录中...' : '登录' }}
          </button>
          
          <p v-if="error" class="text-sm text-red-500 text-center">
            {{ error }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { configApi } from '@/api'

const router = useRouter()
const authStore = useAuthStore()

const token = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  if (!token.value.trim()) return
  
  loading.value = true
  error.value = ''
  
  try {
    // 先设置 token
    authStore.setToken(token.value)
    
    // 验证 token（调用一个需要鉴权的接口）
    await configApi.getRuntimeConfig()
    
    // 验证成功，跳转首页
    router.push('/')
  } catch (err) {
    error.value = err.message || 'Token 验证失败'
    authStore.logout()
  } finally {
    loading.value = false
  }
}
</script>
