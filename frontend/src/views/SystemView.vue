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

    <ForcePasswordDialog v-model:open="forceOpen" @changed="onForcePasswordChanged" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { adminApi, type AppConfigView } from '@/api/admin'
import ForcePasswordDialog from '@/components/ForcePasswordDialog.vue'
import { t, type Lang } from '@/i18n'
import { useUiStore } from '@/stores/ui'

const message = useMessage()
const ui = useUiStore()

let forcePromptShown = false

const pwd = reactive({ old: '', next: '', confirm: '' })
const saving = ref(false)

const langOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
]

const wallpaperPresets = [
  'linear-gradient(135deg, #1d2b3a, #0e1620)',
  'linear-gradient(135deg, #667eea, #764ba2)',
  'linear-gradient(135deg, #11998e, #38ef7d)',
  'linear-gradient(135deg, #ff9966, #ff5e62)',
]

function swatchStyle(p: string) {
  return { backgroundImage: p }
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
const forceOpen = ref(false)

async function loadConfig() {
  if (cfgLoading.value) return
  cfgLoading.value = true
  try {
    config.value = await adminApi.getConfig()
    if (config.value.password_is_default && !forcePromptShown) {
      forcePromptShown = true
      forceOpen.value = true
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    cfgLoading.value = false
  }
}

function onForcePasswordChanged() {
  loadConfig()
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
