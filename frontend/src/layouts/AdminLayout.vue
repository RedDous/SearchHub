<template>
  <n-layout has-sider class="admin-layout">
    <n-layout-sider bordered :width="220" collapse-mode="width" :collapsed-width="64" :collapsed="collapsed" show-trigger @collapse="collapsed = true" @expand="collapsed = false">
      <div class="logo">SearchHub</div>
      <n-menu :value="activeKey" :options="menuOptions" @update:value="onMenuSelect" />
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
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { t } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const collapsed = ref(false)

const menuOptions = computed(() => [
  { label: t('nav.dashboard'), key: 'dashboard' },
  { label: t('nav.providers'), key: 'providers' },
  { label: t('nav.settings'), key: 'settings' },
  { label: t('nav.tokens'), key: 'tokens' },
  { label: t('nav.history'), key: 'history' },
  { label: t('nav.system'), key: 'system' },
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
  await auth.logout()
  router.push({ name: 'login' })
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
