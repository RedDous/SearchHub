<template>
  <div>
    <h1 class="page-title">{{ t('system.title') }}</h1>

    <n-card :title="t('system.changePassword')" class="settings-card">
      <n-form label-placement="left" label-width="160" style="max-width: 520px">
        <n-form-item :label="t('system.oldPassword')">
          <n-input v-model:value="pwd.old" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item :label="t('system.newPassword')">
          <n-input v-model:value="pwd.next" type="password" show-password-on="click" @keyup.enter="onChangePassword" />
        </n-form-item>
        <n-form-item :label="t('system.confirmPassword')">
          <n-input v-model:value="pwd.confirm" type="password" show-password-on="click" @keyup.enter="onChangePassword" />
        </n-form-item>
      </n-form>
      <n-button type="primary" :loading="saving" @click="onChangePassword">{{ t('common.save') }}</n-button>
    </n-card>

    <n-card :title="t('system.configInfo')" class="settings-card">
      <template #header-extra>
        <n-button size="small" :loading="cfgLoading" @click="loadConfig">{{ t('system.refresh') }}</n-button>
      </template>
      <n-descriptions v-if="config" :column="1" label-placement="left" bordered size="small">
        <n-descriptions-item :label="t('system.username')">{{ config.config.admin.username }}</n-descriptions-item>
        <n-descriptions-item :label="t('system.sessionTtl')">{{ config.config.admin.session_ttl_hours }}</n-descriptions-item>
        <n-descriptions-item :label="t('system.configVersion')">{{ config.config_version }}</n-descriptions-item>
        <n-descriptions-item :label="t('system.updatedAt')">{{ new Date(config.updated_at * 1000).toLocaleString() }}</n-descriptions-item>
      </n-descriptions>
    </n-card>

    <n-card :title="t('system.preferences')" class="settings-card">
      <n-form label-placement="left" label-width="160">
        <n-form-item :label="t('system.language')">
          <n-select v-model:value="ui.lang" :options="langOptions" style="max-width: 200px" @update:value="onLangChange" />
        </n-form-item>
        <n-form-item :label="t('system.theme')">
          <n-radio-group v-model:value="ui.theme" @update:value="onThemeChange">
            <n-radio-button value="light">{{ t('system.light') }}</n-radio-button>
            <n-radio-button value="dark">{{ t('system.dark') }}</n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item :label="t('system.wallpaper')">
          <n-space align="center" :size="12" wrap>
            <button
              v-for="p in wallpaperPresets"
              :key="p"
              class="wallpaper-swatch"
              :class="{ active: ui.wallpaper === p }"
              :style="swatchStyle(p)"
              :title="t('system.wallpaper')"
              @click="ui.setWallpaper(p)"
            />
            <n-upload :custom-request="onUpload" :show-file-list="false" accept="image/*">
              <n-button size="small">{{ t('system.wallpaperUpload') }}</n-button>
            </n-upload>
            <n-button v-if="ui.wallpaper" size="small" @click="ui.setWallpaper('')">
              {{ t('system.wallpaperClear') }}
            </n-button>
          </n-space>
        </n-form-item>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { adminApi, type AppConfigView } from '@/api/admin'
import { t, type Lang } from '@/i18n'
import { useUiStore } from '@/stores/ui'

const message = useMessage()
const ui = useUiStore()

const pwd = reactive({ old: '', next: '', confirm: '' })
const saving = ref(false)

const langOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
]

const wallpaperPresets = [
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%231d2b3a'/%3E%3Cstop offset='1' stop-color='%230e1620'/%3E%3C/linearGradient%3E%3Crect width='1600' height='900' fill='url(%23g)'/%3E%3C/svg%3E",
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%23667eea'/%3E%3Cstop offset='1' stop-color='%23764ba2'/%3E%3C/linearGradient%3E%3Crect width='1600' height='900' fill='url(%23g)'/%3E%3C/svg%3E",
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%2311998e'/%3E%3Cstop offset='1' stop-color='%2338ef7d'/%3E%3C/linearGradient%3E%3Crect width='1600' height='900' fill='url(%23g)'/%3E%3C/svg%3E",
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%23ff9966'/%3E%3Cstop offset='1' stop-color='%23ff5e62'/%3E%3C/linearGradient%3E%3Crect width='1600' height='900' fill='url(%23g)'/%3E%3C/svg%3E",
]

function swatchStyle(p: string) {
  return { backgroundImage: `url("${p}")` }
}

function onFile(file: File): boolean {
  if (file.size > 2 * 1024 * 1024) {
    message.error(t('system.wallpaperTooLarge'))
    return false
  }
  const reader = new FileReader()
  reader.onload = () => {
    ui.setWallpaper(String(reader.result))
  }
  reader.onerror = () => {
    message.error(t('common.failed'))
  }
  reader.readAsDataURL(file)
  return true
}

function onUpload(options: UploadCustomRequestOptions) {
  if (options.file.file && onFile(options.file.file)) {
    options.onFinish()
  } else {
    options.onError()
  }
}

function onLangChange(v: Lang) {
  ui.setLang(v)
}

function onThemeChange(v: 'light' | 'dark') {
  ui.setTheme(v)
}

async function onChangePassword() {
  if (pwd.next.length < 8) {
    message.error(t('system.passwordTooShort'))
    return
  }
  if (pwd.next !== pwd.confirm) {
    message.error(t('system.passwordMismatch'))
    return
  }
  saving.value = true
  try {
    await adminApi.changePassword(pwd.old, pwd.next)
    message.success(t('system.passwordChanged'))
    pwd.old = ''
    pwd.next = ''
    pwd.confirm = ''
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    saving.value = false
  }
}

const config = ref<AppConfigView | null>(null)
const cfgLoading = ref(false)

async function loadConfig() {
  if (cfgLoading.value) return
  cfgLoading.value = true
  try {
    config.value = await adminApi.getConfig()
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    cfgLoading.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.page-title {
  margin: 0 0 16px;
  font-size: 20px;
  font-weight: 600;
}
.settings-card {
  margin-bottom: 16px;
}
.wallpaper-swatch {
  width: 48px;
  height: 32px;
  border: 2px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  background-size: cover;
  background-position: center;
  padding: 0;
  outline: none;
}
.wallpaper-swatch.active {
  border-color: #18a058;
}
</style>
