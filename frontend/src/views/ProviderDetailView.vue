<template>
  <div>
    <div class="detail-head">
      <h1 class="page-title">{{ isNew ? (entry?.name ?? t('providers.new')) : form.id }}</h1>
      <n-space>
        <n-button v-if="!isNew" :loading="testing" @click="onTest">
          {{ testing ? t('providers.testing') : t('providers.test') }}
        </n-button>
        <n-button @click="onCancel">{{ t('common.cancel') }}</n-button>
        <n-button type="primary" :loading="saving" @click="onSave">
          {{ t('providers.save') }}
        </n-button>
      </n-space>
    </div>

    <n-spin :show="loading">
      <n-card size="small" class="form-card">
        <n-form label-placement="left" label-width="150">
          <n-form-item :label="t('providers.id')">
            <n-input v-model:value="form.id" :disabled="!isNew || !!entry" :placeholder="isNew && !entry ? 'exa / tavily / ddg / searxng / jina / trafilatura' : ''" />
          </n-form-item>
          <n-form-item :label="t('providers.capabilities')">
            <n-checkbox-group v-model:value="form.capabilities">
              <n-space :size="12">
                <n-checkbox v-for="cap in availableCaps" :key="cap" :value="cap" :label="cap" />
              </n-space>
            </n-checkbox-group>
          </n-form-item>
          <n-form-item :label="t('providers.enabled')">
            <n-switch v-model:value="form.enabled" />
          </n-form-item>
          <n-form-item :label="t('providers.weight')">
            <n-input-number v-model:value="form.weight" :min="1" :max="100" style="width: 160px" />
          </n-form-item>
          <n-form-item :label="t('providers.priority')">
            <n-input-number v-model:value="form.priority" :min="1" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="entry?.show_max_results ?? true" :label="t('providers.maxResults')">
            <n-input-number v-model:value="form.max_results" :min="1" :max="50" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="isNew ? !!entry?.requires_base_url : (!!entry?.requires_base_url || !!form.base_url)" :label="t('providers.baseUrl')">
            <n-input v-model:value="form.base_url" placeholder="http://searxng:8080" />
          </n-form-item>
          <n-form-item v-if="showFullKeyPool" :label="t('providers.maxConcurrency')">
            <n-input-number v-model:value="form.key_pool.max_concurrency" :min="1" :precision="0" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="showFullKeyPool || showRpsOnly" :label="t('providers.rpsLimit')">
            <n-input-number v-model:value="form.key_pool.rps_limit" :min="0.1" :step="0.5" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="showFullKeyPool" :label="t('providers.cooldown')">
            <n-input-number v-model:value="form.key_pool.cooldown_s" :min="0" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="entry?.show_options" :label="t('providers.options')">
            <n-input v-model:value="form.options" type="textarea" :rows="4" placeholder='{"top_k": 5}' />
          </n-form-item>
        </n-form>
      </n-card>

      <n-card v-if="entry?.requires_key || entry?.optional_key || (!entry && !isNew)" :title="t('providers.keyPool')" size="small" class="keys-card">
        <div v-if="entry?.optional_key" class="key-hint-text">{{ t('providers.keyOptionalHint') }}</div>
        <div v-for="k in keys" :key="k.index" class="key-row">
          <n-tag size="small" :bordered="false">{{ k.masked }}</n-tag>
          <n-tag v-if="k.status" size="small" :bordered="false" :type="keyStatus(k).type">
            {{ keyStatus(k).text }}
          </n-tag>
          <n-button size="tiny" type="error" quaternary @click="onDeleteKey(k.index)">
            {{ t('providers.delete') }}
          </n-button>
        </div>
        <div class="key-add">
          <n-input v-model:value="newKey" :placeholder="t('providers.addKey')" @keydown.enter="onAddKey" />
          <n-button type="primary" :loading="addingKey" @click="onAddKey">
            {{ t('providers.addKey') }}
          </n-button>
        </div>
      </n-card>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { adminApi, type KeyEntry, type ProviderCfg } from '@/api/admin'
import { ApiError } from '@/api/client'
import { useProviderTypesStore } from '@/stores/providerTypes'
import { t } from '@/i18n'

const props = defineProps<{ id: string; type?: string }>()
const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const typesStore = useProviderTypesStore()

const isNew = computed(() => props.id === 'new')
const entry = computed(() => (isNew.value ? typesStore.byType(props.type ?? '') : typesStore.byType(form.id)))
const availableCaps = computed(() => entry.value?.capabilities ?? ['search', 'extract'])
const showFullKeyPool = computed(() => entry.value?.key_pool_params === 'full' || (!entry.value && !isNew.value))
const showRpsOnly = computed(() => entry.value?.key_pool_params === 'rps')
// Key 池归属：新建模式用所选类型（secrets.env 的 {TYPE}_KEY_N 前缀），编辑模式用配置 id
const keyId = computed(() => (isNew.value ? props.type ?? '' : props.id))
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const addingKey = ref(false)
const keys = ref<KeyEntry[]>([])
const newKey = ref('')

interface FormModel {
  id: string
  capabilities: string[]
  enabled: boolean
  weight: number
  priority: number
  max_results: number
  base_url: string
  key_pool: { max_concurrency: number; rps_limit: number; cooldown_s: number }
  options: string
}

function emptyForm(): FormModel {
  const catalogType = isNew.value ? typesStore.byType(props.type ?? '') : undefined
  return {
    id: catalogType ? catalogType.type : '',
    capabilities: catalogType ? [...catalogType.capabilities] : ['search', 'extract'],
    enabled: true,
    weight: 10,
    priority: 100,
    max_results: 8,
    base_url: '',
    key_pool: { max_concurrency: 2, rps_limit: 10, cooldown_s: 60 },
    options: '',
  }
}

const form = reactive<FormModel>(emptyForm())

async function load() {
  loading.value = true
  try {
    const cfg = await adminApi.getConfig()
    const p = cfg.config.providers.find((x) => x.id === props.id)
    if (!p) {
      message.error(t('common.failed'))
      return
    }
    form.id = p.id
    form.capabilities = [...p.capabilities]
    form.enabled = p.enabled
    form.weight = p.weight
    form.priority = p.priority
    form.max_results = p.max_results
    form.base_url = p.base_url ?? ''
    form.key_pool = { ...p.key_pool }
    form.options = Object.keys(p.options ?? {}).length ? JSON.stringify(p.options, null, 2) : ''
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    loading.value = false
  }
}

let keysReqSeq = 0

async function loadKeys() {
  if (!keyId.value) {
    keys.value = []
    return
  }
  const seq = ++keysReqSeq
  try {
    const r = await adminApi.listKeys(keyId.value)
    if (seq === keysReqSeq) keys.value = r.keys
  } catch (e) {
    if (seq === keysReqSeq) message.error(e instanceof Error ? e.message : t('common.failed'))
  }
}

function parseOptions(raw: string): Record<string, unknown> {
  if (!raw.trim()) return {}
  try {
    const v = JSON.parse(raw)
    if (typeof v !== 'object' || v === null || Array.isArray(v)) throw new Error('object')
    return v as Record<string, unknown>
  } catch {
    throw new Error(t('providers.invalidJson'))
  }
}

function keyStatus(k: KeyEntry): { type: 'warning' | 'info' | 'success'; text: string } {
  const s = k.status
  if (!s) return { type: 'success', text: '' }
  if (s.cooling_until > 0) return { type: 'warning', text: t('providers.keyStatusCooling') }
  if (s.in_flight > 0) return { type: 'info', text: t('providers.keyStatusBusy') }
  return { type: 'success', text: t('providers.keyStatusOk') }
}

async function onSave() {
  if (isNew.value && !form.id.trim()) {
    message.error(t('providers.idRequired'))
    return
  }
  if (form.capabilities.length === 0) {
    message.error(t('providers.capabilitiesRequired'))
    return
  }
  if (isNew.value && entry.value?.requires_base_url && !form.base_url.trim()) {
    message.error(t('providers.baseUrlRequired'))
    return
  }
  let options: Record<string, unknown>
  try {
    options = parseOptions(form.options)
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
    return
  }
  saving.value = true
  try {
    const cfg: ProviderCfg = {
      id: form.id.trim(),
      capabilities: [...form.capabilities],
      enabled: form.enabled,
      weight: form.weight,
      priority: form.priority,
      max_results: form.max_results,
      base_url: form.base_url.trim() || null,
      key_pool: {
        max_concurrency: form.key_pool.max_concurrency,
        rps_limit: form.key_pool.rps_limit,
        cooldown_s: form.key_pool.cooldown_s,
      },
      options,
    }
    if (isNew.value) {
      await adminApi.createProvider(cfg)
      message.success(t('common.success'))
      router.replace({ name: 'providers' })
      return
    }
    await adminApi.updateProvider(form.id, cfg)
    message.success(t('common.success'))
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      message.error(t('providers.providerExists'))
    } else {
      message.error(e instanceof Error ? e.message : t('common.failed'))
    }
  } finally {
    saving.value = false
  }
}

async function onTest() {
  testing.value = true
  try {
    const r = await adminApi.testProvider(props.id)
    message.success(t('providers.testOk') + `: ${r.capability} × ${r.count} (${r.took_ms}ms)`)
  } catch (e) {
    message.error(t('providers.testFail') + ': ' + (e instanceof Error ? e.message : String(e)))
  } finally {
    testing.value = false
  }
}

function onCancel() {
  router.replace({ name: 'providers' })
}

async function onAddKey() {
  if (!newKey.value.trim() || addingKey.value || !keyId.value) return
  addingKey.value = true
  try {
    await adminApi.addKey(keyId.value, newKey.value.trim())
    newKey.value = ''
    message.success(t('common.success'))
    await loadKeys()
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    addingKey.value = false
  }
}

function onDeleteKey(index: number) {
  dialog.warning({
    title: t('providers.delete'),
    content: t('providers.deleteConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await adminApi.deleteKey(keyId.value, index)
        message.success(t('common.success'))
        await loadKeys()
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('common.failed'))
      }
    },
  })
}

function reload() {
  if (isNew.value) {
    loadKeys()
    return
  }
  load()
  loadKeys()
}

onMounted(async () => {
  await typesStore.load()
  reload()
})
watch(() => props.id, reload)
watch(() => keyId.value, loadKeys)
watch(() => props.type, () => {
  if (isNew.value) Object.assign(form, emptyForm())
})
watch(() => entry.value, (e, prev) => {
  if (isNew.value && !prev && e) {
    Object.assign(form, emptyForm())
    loadKeys()
  }
})
</script>

<style scoped>
.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.form-card {
  margin-bottom: 12px;
}
.keys-card {
  margin-bottom: 12px;
}
.key-hint-text {
  font-size: 13px;
  color: #888;
  margin-bottom: 8px;
}
.key-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.key-add {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
