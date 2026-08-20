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
.logo { padding: 16px; font-weight: 700; font-size: 18px; }
.admin-header { padding: 8px 16px; }
.admin-content { padding: 16px; }
</style>
