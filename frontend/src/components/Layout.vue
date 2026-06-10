<template>
  <div class="min-h-screen bg-bg-secondary">
    <!-- 顶部导航 -->
    <header class="bg-white shadow-sm sticky top-0 z-50">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between items-center h-14">
          <!-- Logo -->
          <div class="flex items-center">
            <router-link to="/" class="text-xl font-bold text-gray-900">
              Stocknew
            </router-link>
          </div>
          
          <!-- 导航菜单 -->
          <nav class="hidden sm:flex space-x-1">
            <router-link
              v-for="item in navItems"
              :key="item.path"
              :to="item.path"
              :class="[
                'px-3 py-2 rounded-md text-sm font-medium transition-colors',
                $route.path === item.path
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              ]"
            >
              {{ item.title }}
              <span
                v-if="item.badge"
                class="ml-1 bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded-full"
              >
                {{ item.badge }}
              </span>
            </router-link>
          </nav>
          
          <!-- 用户操作 -->
          <div class="flex items-center space-x-3">
            <button
              @click="logout"
              class="text-sm text-gray-500 hover:text-gray-700"
            >
              退出
            </button>
          </div>
        </div>
      </div>
      
      <!-- 移动端导航 -->
      <div class="sm:hidden border-t border-gray-200">
        <div class="flex justify-around py-2">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="px-3 py-2 text-xs text-center"
            :class="$route.path === item.path ? 'text-blue-600' : 'text-gray-600'"
          >
            {{ item.title }}
          </router-link>
        </div>
      </div>
    </header>
    
    <!-- 页面内容 -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWatchlistStore } from '@/stores/watchlist'
import { useTailStrategyStore } from '@/stores/tailStrategy'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const watchlistStore = useWatchlistStore()
const tailStrategyStore = useTailStrategyStore()

const navItems = computed(() => [
  { path: '/picks', title: '策略选股' },
  { path: '/tail-strategy', title: '尾盘策略选股', badge: tailStrategyStore.count || undefined },
  { path: '/watchlist', title: '自选股', badge: watchlistStore.count || undefined },
  { path: '/review', title: '策略复盘' },
  { path: '/updates', title: '数据更新' },
  { path: '/data-health', title: '数据详情' }
])

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
