<template>
  <div>
    <div class="providers-head">
      <h1 class="page-title">{{ t('providers.title') }}</h1>
      <n-button type="primary" @click="router.push('/providers/new')">
        {{ t('providers.new') }}
      </n-button>
    </div>

    <n-data-table :columns="columns" :data="providers" :loading="loading" size="small" />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useDialog, useMessage, NButton, NSpace, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { adminApi, type ProviderCfg } from '@/api/admin'
import { t } from '@/i18n'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const loading = ref(false)
const providers = ref<ProviderCfg[]>([])
const keyCounts = ref<Record<string, number>>({})

const columns = computed<DataTableColumns<ProviderCfg>>(() => [
  { title: t('providers.id'), key: 'id' },
  {
    title: t('providers.capabilities'),
    key: 'capabilities',
    render: (row) =>
      h(
        'span',
        row.capabilities.map((c) => h(NTag, { size: 'small', style: 'margin-right: 6px' }, { default: () => c })),
      ),
  },
  {
    title: t('providers.enabled'),
    key: 'enabled',
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.enabled ? 'success' : 'default' },
        { default: () => t(row.enabled ? 'providers.enabledTrue' : 'providers.enabledFalse') },
      ),
  },
  { title: t('providers.weight'), key: 'weight' },
  { title: t('providers.priority'), key: 'priority' },
  { title: t('providers.keys'), key: 'keys', render: (row) => String(keyCounts.value[row.id] ?? 0) },
  {
    title: t('providers.actions'),
    key: 'actions',
    render: (row) =>
      h(NSpace, { size: 6 }, {
        default: () => [
          h(
            NButton,
            { size: 'small', type: 'primary', ghost: true, onClick: () => router.push(`/providers/${row.id}`) },
            { default: () => t('providers.view') },
          ),
          h(
            NButton,
            { size: 'small', type: 'error', ghost: true, onClick: () => onDelete(row) },
            { default: () => t('providers.delete') },
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

onMounted(load)
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
</style>
