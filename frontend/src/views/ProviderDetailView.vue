<template>
  <div>
    <div class="detail-head">
      <div class="detail-title">
        <div class="title-row">
          <h1 class="page-title">{{ isNew ? (entry?.name ?? t('providers.new')) : form.id }}</h1>
          <n-tag v-if="lastStatus" size="small" :type="badgeType" :title="badgeTitle">
            {{ badgeText }}
          </n-tag>
        </div>
        <div v-if="entry?.description_key" class="provider-desc">
          {{ t(entry.description_key) }}
        </div>
        <a
          v-if="entry?.docs_url"
          class="provider-docs"
          :href="entry.docs_url"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ t('providers.docs') }}
        </a>
      </div>
      <n-space>
        <n-button :loading="testing" :disabled="isNew && !entry"
                  :title="isNew && !entry ? t('providers.testUnsupported') : undefined" @click="onTest">
          {{ testing ? t('providers.testing') : t('providers.test') }}
        </n-button>
        <n-button @click="onCancel">{{ t('providers.back') }}</n-button>
        <n-button type="primary" :loading="saving" @click="onSave">
          {{ t('providers.save') }}
        </n-button>
      </n-space>
    </div>

    <n-card v-if="testResults.length" size="small" class="test-card" :title="t('providers.testResults')">
      <div v-for="result in testResults" :key="result.capability" class="test-row">
        <n-tag size="small" :type="result.success ? 'success' : 'error'">{{ result.capability }}</n-tag>
        <span v-if="result.success" class="test-summary">
          {{ result.count }} · {{ result.took_ms }}ms
        </span>
        <span v-else class="test-error">{{ result.error || t('providers.testFailShort') }}</span>
      </div>
    </n-card>

    <n-spin :show="loading">
      <n-card size="small" class="form-card">
        <n-form label-placement="left" label-width="150">
          <n-form-item :label="t('providers.type')">
            <n-input :value="form.type" disabled />
          </n-form-item>
          <n-form-item :label="t('providers.id')">
            <n-input v-model:value="form.id" :disabled="!isNew || !!entry" :placeholder="form.type" />
          </n-form-item>
          <n-form-item :label="t('providers.capabilities')">
            <n-checkbox-group v-model:value="form.capabilities">
              <n-space :size="12">
                <n-checkbox v-for="cap in availableCaps" :key="cap" :value="cap" :label="cap"
                            :disabled="availableCaps.length === 1" />
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
          <n-form-item v-if="showBaseUrl" :label="t('providers.baseUrl')"
                       :required="!!entry?.endpoint.required">
            <n-input v-model:value="form.base_url" :placeholder="baseUrlPlaceholder" />
          </n-form-item>

          <template v-if="hasOptions">
            <n-divider>{{ t('providers.options') }}</n-divider>
            <ProviderOptionsForm
              v-model:options="form.options"
              :fields="entry?.fields ?? []"
              :capabilities="form.capabilities"
            />
          </template>

          <n-collapse v-model:expanded-names="jsonExpanded" class="json-fallback">
            <n-collapse-item :title="t('providers.advancedJson')" name="json">
              <div class="json-hint">{{ t('providers.advancedJsonHelp') }}</div>
              <n-input
                v-model:value="jsonDraft"
                type="textarea"
                :rows="6"
                :status="jsonError ? 'error' : undefined"
                @focus="jsonEditing = true"
                @blur="applyJsonDraft"
              />
              <div v-if="jsonError" class="json-error">{{ jsonError }}</div>
            </n-collapse-item>
          </n-collapse>
        </n-form>
      </n-card>

      <n-card v-if="showKeyPool" :title="keysCardTitle" size="small" class="keys-card">
        <div v-if="entry?.auth.optional" class="key-hint-text">{{ t('providers.keyOptionalHint') }}</div>
        <n-form label-placement="left" label-width="150">
          <n-form-item v-if="showFullKeyPool" :label="t('providers.maxConcurrency')">
            <n-input-number v-model:value="form.key_pool.max_concurrency" :min="1" :precision="0" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="showFullKeyPool || showRpsOnly" :label="t('providers.rpsLimit')">
            <n-input-number v-model:value="form.key_pool.rps_limit" :min="0.1" :step="0.5" style="width: 160px" />
          </n-form-item>
          <n-form-item v-if="showFullKeyPool" :label="t('providers.cooldown')">
            <n-input-number v-model:value="form.key_pool.cooldown_s" :min="0" style="width: 160px" />
          </n-form-item>
        </n-form>
        <template v-if="showKeyRows">
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
        </template>
      </n-card>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import {
  adminApi,
  type KeyEntry,
  type ProviderCfg,
  type ProviderStatus,
  type ProviderTest,
  type ProviderTestResult,
} from '@/api/admin'
import { ApiError } from '@/api/client'
import { useProviderTypesStore } from '@/stores/providerTypes'
import { buildProviderPayload, defaultOptions } from '@/utils/providerPayload'
import { shouldShowKeyPool, shouldShowKeyRows } from '@/utils/providerFields'
import { t } from '@/i18n'
import ProviderOptionsForm from '@/components/ProviderOptionsForm.vue'

const props = defineProps<{ id: string; type?: string }>()
const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const typesStore = useProviderTypesStore()

const isNew = computed(() => props.id === 'new')
const entry = computed(() => (isNew.value ? typesStore.byType(props.type ?? '') : typesStore.byType(form.type)))
const availableCaps = computed(() => entry.value?.capabilities ?? ['search', 'extract'])
const showBaseUrl = computed(
  () =>
    entry.value?.endpoint.overridable ||
    entry.value?.endpoint.required ||
    (!entry.value && !isNew.value),
)
const baseUrlPlaceholder = computed(
  () => entry.value?.endpoint.placeholder || entry.value?.endpoint.default || 'http://searxng:8080',
)
const showKeyPool = computed(() =>
  entry.value ? shouldShowKeyPool(entry.value) : !isNew.value,
)
const showKeyRows = computed(() =>
  entry.value ? shouldShowKeyRows(entry.value) : !isNew.value,
)
const keysCardTitle = computed(() =>
  showKeyRows.value ? t('providers.keyPool') : t('providers.rateLimit'),
)
const showFullKeyPool = computed(() => entry.value?.key_pool_params === 'full' || (!entry.value && !isNew.value))
const showRpsOnly = computed(() => entry.value?.key_pool_params === 'rps')
const hasOptions = computed(() => (entry.value?.fields.length ?? 0) > 0)
// Key 池归属：新建模式用所选类型（secrets.env 的 {TYPE}_KEY_N 前缀），编辑模式用配置 id
const keyId = computed(() => (isNew.value ? props.type ?? '' : props.id))
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const lastStatus = ref<ProviderStatus | null>(null)
const testResults = ref<ProviderTestResult[]>([])
const addingKey = ref(false)
const keys = ref<KeyEntry[]>([])
const newKey = ref('')
const jsonExpanded = ref<string | number | Array<string | number> | null>(null)
const jsonDraft = ref('')
const jsonError = ref('')
const jsonEditing = ref(false)

interface FormModel {
  id: string
  type: string
  capabilities: string[]
  enabled: boolean
  weight: number
  priority: number
  max_results: number
  base_url: string
  key_pool: { max_concurrency: number; rps_limit: number; cooldown_s: number }
  options: Record<string, unknown>
}

function emptyForm(): FormModel {
  const catalogType = isNew.value ? typesStore.byType(props.type ?? '') : undefined
  const type = catalogType ? catalogType.type : (props.type ?? '')
  return {
    id: type,
    type,
    capabilities: catalogType ? [...catalogType.capabilities] : ['search', 'extract'],
    enabled: true,
    weight: 10,
    priority: 100,
    max_results: 8,
    base_url: '',
    key_pool: { max_concurrency: 2, rps_limit: 10, cooldown_s: 60 },
    options: catalogType ? defaultOptions(catalogType.fields) : {},
  }
}

/** Defaults from the catalog, overlaid with the values saved on disk. */
function optionsWithDefaults(type: string, saved: Record<string, unknown>): Record<string, unknown> {
  const catalogType = typesStore.byType(type)
  return { ...(catalogType ? defaultOptions(catalogType.fields) : {}), ...saved }
}

const form = reactive<FormModel>(emptyForm())

watch(
  () => form.options,
  (value) => {
    if (jsonEditing.value) return
    jsonDraft.value = JSON.stringify(value ?? {}, null, 2)
    jsonError.value = ''
  },
  { deep: true, immediate: true },
)

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
    form.type = p.type
    form.capabilities = [...p.capabilities]
    form.enabled = p.enabled
    form.weight = p.weight
    form.priority = p.priority
    form.max_results = p.max_results
    form.base_url = p.base_url ?? ''
    form.key_pool = { ...p.key_pool }
    form.options = optionsWithDefaults(p.type, p.options ?? {})
    const st = cfg.provider_status[props.id] ?? null
    lastStatus.value = st
    testResults.value = st
      ? Object.entries(st.tests ?? {}).map(([capability, test]) => ({
          capability: test.capability || capability,
          success: test.success,
          count: test.count ?? 0,
          took_ms: test.took_ms ?? 0,
          error: test.error,
        }))
      : []
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
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error(t('providers.invalidJson'))
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error(t('providers.invalidJson'))
  }
  return parsed as Record<string, unknown>
}

function isJsonOpen(): boolean {
  const expanded = jsonExpanded.value
  if (Array.isArray(expanded)) return expanded.includes('json')
  return expanded === 'json'
}

/**
 * Options to submit. When the advanced JSON fallback is open its contents are
 * authoritative and validated before any request is made.
 */
function currentOptions(): Record<string, unknown> {
  if (!isJsonOpen()) return form.options
  const parsed = parseOptions(jsonDraft.value)
  form.options = parsed
  jsonError.value = ''
  return parsed
}

function applyJsonDraft() {
  jsonEditing.value = false
  try {
    const parsed = parseOptions(jsonDraft.value)
    form.options = parsed
    jsonError.value = ''
    jsonDraft.value = JSON.stringify(parsed, null, 2)
  } catch (e) {
    jsonError.value = e instanceof Error ? e.message : t('providers.invalidJson')
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
  if (entry.value?.endpoint.required && !form.base_url.trim()) {
    message.error(t('providers.baseUrlRequired'))
    return
  }
  let options: Record<string, unknown>
  try {
    options = currentOptions()
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
    return
  }
  saving.value = true
  try {
    const cfg = buildProviderPayload({ ...form, options })
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

function recordTestResults(results: ProviderTestResult[]) {
  testResults.value = results
  const at = Date.now() / 1000
  const tests: Record<string, ProviderTest> = {}
  for (const result of results) tests[result.capability] = { ...result, at }
  const first = results[0]
  lastStatus.value = {
    status:
      results.length === 0 ? 'untested' : results.some((r) => !r.success) ? 'failed' : 'ok',
    test: first ? { ...first, at } : null,
    tests,
  }
}

async function onTest() {
  if (testing.value) return
  let options: Record<string, unknown>
  try {
    options = currentOptions()
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
    return
  }
  testing.value = true
  try {
    const r = isNew.value
      ? await adminApi.testProviderConfig(buildProviderPayload({ ...form, options }))
      : await adminApi.testProvider(props.id)
    recordTestResults(r.results)
    const failed = r.results.filter((x) => !x.success)
    if (failed.length) {
      message.error(t('providers.testFail') + ': ' + (failed[0].error || failed[0].capability))
    } else {
      message.success(t('providers.testOk'))
    }
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e)
    lastStatus.value = {
      status: 'failed',
      test: { success: false, error: detail, at: Date.now() / 1000 },
      tests: {},
    }
    testResults.value = []
    message.error(t('providers.testFail') + ': ' + detail + (isNew.value ? t('providers.testDraftHint') : ''))
  } finally {
    testing.value = false
  }
}

function testSummary(): string {
  const tests = Object.values(lastStatus.value?.tests ?? {})
  if (tests.length === 0) return lastStatus.value?.test?.error ?? ''
  return tests
    .map((x) =>
      x.success
        ? `${x.capability} × ${x.count} (${x.took_ms}ms)`
        : `${x.capability}: ${x.error ?? t('providers.testFailShort')}`,
    )
    .join('\n')
}

const badgeMap: Record<string, { type: string; text: string; title: () => string }> = {
  ok: { type: 'success', text: t('providers.testOkShort'), title: testSummary },
  failed: { type: 'error', text: t('providers.testFailShort'), title: testSummary },
  untested: { type: 'default', text: t('providers.testNever'), title: () => '' },
  invalid_config: { type: 'error', text: t('providers.invalidConfig'), title: () => '' },
  missing_key: { type: 'error', text: t('providers.missingKey'), title: () => '' },
  missing_base_url: { type: 'error', text: t('providers.missingBaseUrl'), title: () => '' },
}
const badgeType = computed(() => badgeMap[lastStatus.value?.status ?? '']?.type ?? 'default')
const badgeText = computed(() => badgeMap[lastStatus.value?.status ?? '']?.text ?? '')
const badgeTitle = computed(() => badgeMap[lastStatus.value?.status ?? '']?.title() ?? '')

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
    lastStatus.value = null
    testResults.value = []
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
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 16px;
}
.detail-title {
  min-width: 0;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.provider-desc {
  margin-top: 6px;
  font-size: 13px;
  color: #666;
}
.provider-docs {
  display: inline-block;
  margin-top: 4px;
  font-size: 13px;
}
.form-card {
  margin-bottom: 12px;
}
.test-card {
  margin-bottom: 12px;
}
.test-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.test-summary {
  font-size: 13px;
  color: #666;
}
.test-error {
  font-size: 13px;
  color: #d03050;
  word-break: break-word;
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
.json-fallback {
  margin-top: 16px;
}
.json-hint {
  font-size: 12px;
  color: #888;
  margin-bottom: 6px;
}
.json-error {
  margin-top: 4px;
  font-size: 12px;
  color: #d03050;
}
</style>
