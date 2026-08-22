import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
      { path: 'providers', name: 'providers', component: () => import('@/views/ProvidersView.vue') },
      { path: 'providers/new/:type', name: 'provider-new', component: () => import('@/views/ProviderDetailView.vue'), props: (route: RouteLocationNormalized) => ({ id: 'new', type: String(route.params.type) }) },
      { path: 'providers/:id', name: 'provider-detail', component: () => import('@/views/ProviderDetailView.vue'), props: true },
      { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
      { path: 'tokens', name: 'tokens', component: () => import('@/views/TokensView.vue') },
      { path: 'history', name: 'history', component: () => import('@/views/HistoryView.vue') },
      { path: 'system', name: 'system', component: () => import('@/views/SystemView.vue') },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.loggedIn) return { name: 'dashboard' }
    return true
  }
  if (!auth.loggedIn) {
    await auth.checkSession()
  }
  if (!auth.loggedIn) return { name: 'login' }
  return true
})
