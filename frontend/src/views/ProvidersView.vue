<template>
  <div>
    <div class="providers-head">
      <h1 class="page-title">{{ t('providers.title') }}</h1>
    </div>

    <h2 class="section-title">{{ t('providers.configuredTitle') }}</h2>
    <n-data-table :columns="columns" :data="providers" :loading="loading" size="small" />

    <h2 class="section-title">{{ t('providers.catalogTitle') }}</h2>
    <n-alert v-if="typesStore.error" type="error" :show-icon="false" class="catalog-error">
      {{ typesStore.error }}
    </n-alert>
    <n-grid :cols="3" responsive="screen" :x-gap="12" :y-gap="12">
      <n-grid-item v-for="entry in typesStore.types" :key="entry.type">
        <n-card size="small" hoverable class="catalog-card" @click="onCatalogClick(entry)">
          <div class="catalog-name">
            {{ entry.name }}
            <n-tag size="small" :type="isConfigured(entry.type) ? 'success' : 'default'">
              {{ t(isConfigured(entry.type) ? 'providers.configured' : 'providers.unconfigured') }}
            </n-tag>
          </div>
          <div class="catalog-desc">{{ t('providers.desc.' + entry.type) }}</div>
          <n-space :size="6">
            <n-tag v-for="c in entry.capabilities" :key="c" size="small" :bordered="false">
              {{ c }}
            </n-tag>
          </n-space>
        </n-card>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useDialog, useMessage, NButton, NSpace, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { adminApi, type ProviderCfg, type ProviderTest, type ProviderType } from '@/api/admin'
import { useProviderTypesStore } from '@/stores/providerTypes'
import { t } from '@/i18n'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const typesStore = useProviderTypesStore()
const loading = ref(false)
const providers = ref<ProviderCfg[]>([])
const keyCounts = ref<Record<string, number>>({})
const configTests = ref<Record<string, ProviderTest>>({})

const configuredIds = computed(() => new Set(providers.value.map((p) => p.id)))

function isConfigured(type: string): boolean {
  return configuredIds.value.has(type)
}

function onCatalogClick(entry: ProviderType) {
  const configured = configuredIds.value.has(entry.type)
  router.push(configured ? { name: 'provider-detail', params: { id: entry.type } } : { name: 'provider-new', params: { type: entry.type } })
}

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
  {
    title: t('providers.availability'),
    key: 'availability',
    render: (row) => {
      const test = configTests.value[row.id]
      if (!test) return h(NTag, { size: 'small', type: 'default' }, { default: () => t('providers.testNever') })
      if (test.success) return h(NTag, { size: 'small', type: 'success' }, { default: () => t('providers.testOkShort') })
      return h(NTag, { size: 'small', type: 'error' }, { default: () => t('providers.testFailShort') })
    },
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
    configTests.value = cfg.provider_tests
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
.section-title {
  margin: 20px 0 12px;
  font-size: 16px;
  font-weight: 600;
}
.catalog-card {
  cursor: pointer;
}
.catalog-error {
  margin-bottom: 12px;
}
.catalog-name {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 6px;
}
.catalog-desc {
  font-size: 13px;
  color: #888;
  margin-bottom: 8px;
}
</style>
