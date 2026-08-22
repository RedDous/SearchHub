<template>
  <n-layout has-sider class="admin-layout">
    <n-layout-sider bordered :width="220" collapse-mode="width" :collapsed-width="64" :collapsed="collapsed" show-trigger @collapse="collapsed = true" @expand="collapsed = false">
<div class="logo">SearchHub</div>
        <n-menu :value="activeKey" :options="menuOptions" :collapsed="collapsed" :collapsed-width="64" :collapsed-icon-size="20" @update:value="onMenuSelect" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="admin-header">
        <n-space align="center" justify="end">
          <n-select v-model:value="ui.lang" :options="langOptions" size="small" style="width: 110px" @update:value="onLangChange" />
          <n-button quaternary size="small" @click="toggleTheme">
            {{ ui.theme === 'dark' ? '☀️' : '🌙' }}
          </n-button>
          <n-button quaternary size="small" @click="onLogout">{{ t('nav.logout') }}</n-button>
        </n-space>
      </n-layout-header>
      <n-layout-content class="admin-content">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, h, ref, type Component } from 'vue'
import { NIcon } from 'naive-ui'
import {
  CogOutline,
  GridOutline,
  KeyOutline,
  ServerOutline,
  SettingsOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import { useRoute, useRouter } from 'vue-router'
import { t } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const collapsed = ref(false)

function icon(component: Component) {
  return () => h(NIcon, null, { default: () => h(component) })
}

const menuOptions = computed(() => [
  { label: t('nav.dashboard'), key: 'dashboard', icon: icon(GridOutline) },
  { label: t('nav.providers'), key: 'providers', icon: icon(ServerOutline) },
  { label: t('nav.settings'), key: 'settings', icon: icon(SettingsOutline) },
  { label: t('nav.tokens'), key: 'tokens', icon: icon(KeyOutline) },
  { label: t('nav.history'), key: 'history', icon: icon(TimeOutline) },
  { label: t('nav.system'), key: 'system', icon: icon(CogOutline) },
])
const activeKey = computed(() => String(route.name ?? 'dashboard'))
const langOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
]

function onMenuSelect(key: string) {
  router.push({ name: key })
}
function onLangChange(v: 'zh' | 'en') {
  ui.setLang(v)
}
function toggleTheme() {
  ui.setTheme(ui.theme === 'dark' ? 'light' : 'dark')
}
async function onLogout() {
  try {
    await auth.logout()
  } finally {
    router.push({ name: 'login' })
  }
}
</script>

<style scoped>
.admin-layout {
  height: 100vh;
  background-image: var(--sh-wallpaper, none);
  background-size: cover;
  background-position: center;
}
/* 磨玻璃：侧边栏 / 顶栏 / 内容卡片半透明 + 背景模糊，与壁纸协调 */
.admin-layout :deep(.n-layout),
.admin-layout :deep(.n-layout-header),
.admin-layout :deep(.n-layout-content),
.admin-layout :deep(.n-layout-scroll-container) {
  background: transparent;
}
.admin-layout :deep(.n-layout-sider) {
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(14px) saturate(1.5);
}
.admin-layout :deep(.n-layout-header) {
  background: rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(10px) saturate(1.5);
}
.dark .admin-layout :deep(.n-layout-sider) {
  background: rgba(18, 22, 30, 0.6);
}
.dark .admin-layout :deep(.n-layout-header) {
  background: rgba(18, 22, 30, 0.5);
}
/* 内容卡片与表格磨玻璃 */
.admin-content :deep(.n-card) {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(12px) saturate(1.4);
}
.admin-content :deep(.n-data-table),
.admin-content :deep(.n-data-table .n-data-table-base-table) {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px) saturate(1.4);
}
.dark .admin-content :deep(.n-card) {
  background: rgba(18, 22, 30, 0.72);
}
.dark .admin-content :deep(.n-data-table),
.dark .admin-content :deep(.n-data-table .n-data-table-base-table) {
  background: rgba(18, 22, 30, 0.66);
}
/* 顶栏控件（语言选择等）半透明，明暗两态协调 */
.admin-header :deep(.n-base-selection) {
  background: rgba(255, 255, 255, 0.4);
  backdrop-filter: blur(8px);
}
.dark .admin-header :deep(.n-base-selection) {
  background: rgba(255, 255, 255, 0.08);
}
.logo { padding: 16px; font-weight: 700; font-size: 18px; }
.admin-header { padding: 8px 16px; }
.admin-content { padding: 16px; }
</style>
