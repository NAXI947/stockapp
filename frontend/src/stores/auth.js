import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', () => {
  // 从 localStorage 读取 token
  const token = ref(localStorage.getItem('api_token') || '')
  const isLocalDesktop = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
  
  const isAuthenticated = computed(() => isLocalDesktop || !!token.value)
  
  function setToken(newToken) {
    token.value = newToken
    localStorage.setItem('api_token', newToken)
  }
  
  function logout() {
    token.value = ''
    localStorage.removeItem('api_token')
  }
  
  return {
    token,
    isAuthenticated,
    setToken,
    logout
  }
})
