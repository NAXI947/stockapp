import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('@/components/Layout.vue'),
    redirect: '/picks',
    children: [
      {
        path: '/picks',
        name: 'Picks',
        component: () => import('@/views/Picks.vue'),
        meta: { title: '策略选股' }
      },
      {
        path: '/stock/:tsCode',
        name: 'StockDetail',
        component: () => import('@/views/StockDetail.vue'),
        meta: { title: '个股分析' }
      },
      {
        path: '/watchlist',
        name: 'Watchlist',
        component: () => import('@/views/Watchlist.vue'),
        meta: { title: '自选股' }
      },
      {
        path: '/tail-strategy',
        name: 'TailStrategy',
        component: () => import('@/views/TailStrategy.vue'),
        meta: { title: '尾盘策略选股' }
      },
      {
        path: '/review',
        name: 'Review',
        component: () => import('@/views/Review.vue'),
        meta: { title: '策略复盘' }
      },
      {
        path: '/updates',
        name: 'DataUpdate',
        component: () => import('@/views/DataUpdate.vue'),
        meta: { title: '数据更新' }
      },
      {
        path: '/data-health',
        name: 'DataHealth',
        component: () => import('@/views/DataHealth.vue'),
        meta: { title: '数据详情' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  
  if (!to.meta.public && !authStore.isAuthenticated) {
    next('/login')
  } else {
    next()
  }
})

export default router
