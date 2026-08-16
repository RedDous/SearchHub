<template>
  <n-config-provider :locale="naiveLocale" :theme="theme">
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
import { computed } from 'vue'
import {
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  NNotificationProvider,
  darkTheme,
  type GlobalTheme,
} from 'naive-ui'
import { naiveLocale } from '@/i18n'

const isDark = computed(() => localStorage.getItem('sh_theme') === 'dark')
const theme = computed<GlobalTheme | null>(() => (isDark.value ? darkTheme : null))
</script>
