<template>
  <div>
    <h1 class="page-title">{{ t('settings.title') }}</h1>

    <n-card :title="t('settings.strategy')" class="settings-card">
      <n-form label-placement="left" label-width="200">
        <n-form-item :label="t('settings.defaultMode')">
          <n-select v-model:value="form.strategy.default_mode" :options="modeOptions" style="max-width: 320px" />
        </n-form-item>
        <n-form-item :label="t('settings.timeout')">
          <n-input-number v-model:value="form.strategy.timeout_s" :min="0.5" :max="120" :step="0.5" style="max-width: 200px" />
        </n-form-item>
      </n-form>
    </n-card>

    <n-card :title="t('settings.cache')" class="settings-card">
      <n-form label-placement="left" label-width="200">
        <n-form-item :label="t('settings.cacheEnabled')">
          <n-switch v-model:value="form.cache.enabled" />
        </n-form-item>
        <n-form-item :label="t('settings.searchTtl')">
          <n-input-number v-model:value="form.cache.search_ttl_s" :min="0" style="max-width: 200px" />
        </n-form-item>
        <n-form-item :label="t('settings.extractTtl')">
          <n-input-number v-model:value="form.cache.extract_ttl_s" :min="0" style="max-width: 200px" />
        </n-form-item>
      </n-form>
    </n-card>

    <n-card :title="t('settings.history')" class="settings-card">
      <n-form label-placement="left" label-width="200">
        <n-form-item :label="t('settings.retentionDays')">
          <n-input-number v-model:value="form.history.retention_days" :min="1" :max="3650" style="max-width: 200px" />
        </n-form-item>
        <n-form-item :label="t('settings.redactQueries')">
          <n-switch v-model:value="form.history.redact_queries" />
        </n-form-item>
      </n-form>
    </n-card>

    <n-button type="primary" :loading="saving" @click="onSave">{{ t('settings.save') }}</n-button>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { adminApi } from '@/api/admin'
import { t } from '@/i18n'

const message = useMessage()
const saving = ref(false)
const modeOptions = computed(() => [
  { label: t('settings.modeFanout'), value: 'fanout' },
  { label: t('settings.modeRotation'), value: 'rotation' },
  { label: t('settings.modePrimaryFallback'), value: 'primary_fallback' },
])

const form = reactive({
  strategy: { default_mode: 'fanout', timeout_s: 5 },
  cache: { enabled: false, search_ttl_s: 0, extract_ttl_s: 0 },
  history: { retention_days: 30, redact_queries: false },
})

async function load() {
  try {
    const cfg = await adminApi.getConfig()
    Object.assign(form.strategy, cfg.config.strategy)
    Object.assign(form.cache, cfg.config.cache)
    Object.assign(form.history, cfg.config.history)
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  }
}

async function onSave() {
  saving.value = true
  try {
    await adminApi.updateSettings({
      strategy: { ...form.strategy },
      cache: { ...form.cache },
      history: { ...form.history },
    })
    message.success(t('settings.saved'))
    await load()
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
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
</style>
