<template>
  <div>
    <div class="providers-head">
      <h1 class="page-title">{{ t('providers.title') }}</h1>
    </div>

    <n-alert v-if="typesStore.error" type="error" :show-icon="false" class="catalog-error">
      {{ typesStore.error }}
    </n-alert>
    <n-data-table :columns="columns" :data="rows" :loading="loading" size="small" />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useDialog, useMessage, NButton, NSpace, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { adminApi, type ProviderCfg, type ProviderStatus } from '@/api/admin'
import { useProviderTypesStore } from '@/stores/providerTypes'
import { t } from '@/i18n'

type Row =
  | (ProviderCfg & { configured: true; name: string })
  | { id: string; name: string; capabilities: string[]; configured: false }

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const typesStore = useProviderTypesStore()
const loading = ref(false)
const providers = ref<ProviderCfg[]>([])
const keyCounts = ref<Record<string, number>>({})
const configStatus = ref<Record<string, ProviderStatus>>({})

const rows = computed<Row[]>(() => {
  const cfg = new Map(providers.value.map((p) => [p.id, p]))
  const list = typesStore.types.map((entry) => {
    const p = cfg.get(entry.type)
    return p
      ? { ...p, configured: true as const, name: entry.name }
      : { id: entry.type, name: entry.name, capabilities: entry.capabilities, configured: false as const }
  })
  const catalogIds = new Set(typesStore.types.map((e) => e.type))
  for (const p of providers.value) {
    if (!catalogIds.has(p.id)) {
      list.push({ ...p, configured: true as const, name: p.id })
    }
  }
  return list
})

const statusTag = computed(() => (id: string, configured: boolean) => {
  if (!configured) return h(NTag, { size: 'small', type: 'default' }, { default: () => t('providers.unconfigured') })
  const st = configStatus.value[id]
  if (!st) return h(NTag, { size: 'small', type: 'default' }, { default: () => t('providers.testNever') })
  const map: Record<string, ['success' | 'error' | 'default', string]> = {
    ok: ['success', t('providers.testOkShort')],
    failed: ['error', t('providers.testFailShort')],
    untested: ['default', t('providers.testNever')],
    missing_key: ['error', t('providers.missingKey')],
    missing_base_url: ['error', t('providers.missingBaseUrl')],
  }
  const [type, text] = map[st.status] ?? ['default', st.status]
  return h(NTag, { size: 'small', type }, { default: () => text })
})

const columns = computed<DataTableColumns<Row>>(() => [
  {
    title: t('providers.id'),
    key: 'id',
    render: (row) => h('span', { class: 'provider-cell' }, [
      h('span', { class: 'provider-name' }, row.name),
      h('span', { class: 'provider-sub' }, row.id),
    ]),
  },
  {
    title: t('providers.availability'),
    key: 'availability',
    render: (row) => statusTag.value(row.id, row.configured),
  },
  {
    title: t('providers.capabilities'),
    key: 'capabilities',
    render: (row) =>
      h(
        'span',
        row.capabilities.map((c) => h(NTag, { size: 'small', style: 'margin-right: 6px' }, { default: () => c })),
      ),
  },
  { title: t('providers.keys'), key: 'keys', render: (row) => (row.configured ? String(keyCounts.value[row.id] ?? 0) : '—') },
  { title: t('providers.weight'), key: 'weight', render: (row) => (row.configured ? String(row.weight) : '—') },
  { title: t('providers.priority'), key: 'priority', render: (row) => (row.configured ? String(row.priority) : '—') },
  {
    title: t('providers.actions'),
    key: 'actions',
    render: (row) =>
      h(NSpace, { size: 6 }, {
        default: () =>
          row.configured
            ? [
                h(
                  NButton,
                  { size: 'small', type: 'primary', ghost: true, onClick: () => router.push(`/providers/${row.id}`) },
                  { default: () => t('providers.view') },
                ),
                h(
                  NButton,
                  { size: 'small', type: 'error', ghost: true, onClick: () => onDelete(row as ProviderCfg) },
                  { default: () => t('providers.delete') },
                ),
              ]
            : [
                h(
                  NButton,
                  { size: 'small', type: 'primary', onClick: () => router.push({ name: 'provider-new', params: { type: row.id } }) },
                  { default: () => t('providers.add') },
                ),
              ],
      }),
  },
])

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const cfg = await adminApi.getConfig()
    providers.value = cfg.config.providers
    configStatus.value = cfg.provider_status
    const counts = await Promise.all(
      cfg.config.providers.map(async (p) => {
        try {
          const r = await adminApi.listKeys(p.id)
          return [p.id, r.keys.length] as const
        } catch {
          return [p.id, 0] as const
        }
      }),
    )
    keyCounts.value = Object.fromEntries(counts)
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    loading.value = false
  }
}

function onDelete(row: ProviderCfg) {
  dialog.warning({
    title: t('providers.delete'),
    content: t('providers.deleteProviderConfirm').replace('{id}', row.id),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await adminApi.deleteProvider(row.id)
        message.success(t('common.success'))
        await load()
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('common.failed'))
      }
    },
  })
}

onMounted(() => {
  typesStore.load()
  load()
})
</script>

<style scoped>
.providers-head {
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
.catalog-error {
  margin-bottom: 12px;
}
.provider-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.provider-name {
  font-weight: 600;
}
.provider-sub {
  font-size: 12px;
  color: #888;
}
</style>