<template>
  <n-config-provider :theme="naiveTheme" :locale="naiveLocale" :date-locale="naiveDateLocale">
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <router-view />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import {
  darkTheme,
  dateEnUS,
  dateZhCN,
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  NNotificationProvider,
} from 'naive-ui'
import { naiveLocale, type Lang } from '@/i18n'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const naiveTheme = computed(() => (ui.theme === 'dark' ? darkTheme : null))
const naiveDateLocale = computed(() => (ui.lang === 'zh' ? dateZhCN : dateEnUS))

function applyWallpaper() {
  const w = ui.wallpaper
  if (w) {
    // 渐变/CSS 值或已带 url() 包装的按原样应用；图片 URL/dataURL 需包一层 url()
    const isCssValue = w.startsWith('linear-gradient(') || w.startsWith('radial-gradient(') || w.startsWith('url(')
    const value = isCssValue ? w : `url("${w}")`
    document.documentElement.style.setProperty('--sh-wallpaper', value)
  } else {
    document.documentElement.style.removeProperty('--sh-wallpaper')
  }
}

function applyTheme(theme: 'light' | 'dark') {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

onMounted(() => {
  ui.setLang(ui.lang as Lang)
  applyWallpaper()
  applyTheme(ui.theme)
})

watch(() => ui.wallpaper, applyWallpaper)
watch(() => ui.theme, (v) => applyTheme(v))
</script>
