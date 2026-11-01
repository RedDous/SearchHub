<template>
  <div>
    <div class="providers-head">
      <h1 class="page-title">{{ t('providers.title') }}</h1>
      <n-button-group size="small">
        <n-button :type="viewMode === 'card' ? 'primary' : 'default'" @click="viewMode = 'card'">
          {{ t('providers.cardView') }}
        </n-button>
        <n-button :type="viewMode === 'table' ? 'primary' : 'default'" @click="viewMode = 'table'">
          {{ t('providers.tableView') }}
        </n-button>
      </n-button-group>
    </div>

    <n-alert v-if="typesStore.error" type="error" :show-icon="false" class="catalog-error">
      {{ typesStore.error }}
    </n-alert>
    <n-spin :show="loading">
      <template v-if="viewMode === 'card'">
        <n-grid :cols="3" responsive="screen" :x-gap="12" :y-gap="12">
          <n-grid-item v-for="row in rows" :key="row.id">
            <n-card size="small" class="provider-card">
              <div class="card-top">
                <div class="card-heading">
                  <div class="card-name">{{ row.name }}</div>
                  <div class="card-instance">
                    <template v-if="row.configured">
                      {{ t('providers.id') }}: {{ row.id }} · {{ t('providers.type') }}: {{ row.type }}
                    </template>
                    <template v-else>
                      {{ t('providers.type') }}: {{ row.type }}
                    </template>
                  </div>
                </div>
                <StatusTag :status="row.status" :configured="row.configured" />
              </div>
              <div v-if="row.descriptionKey" class="card-desc">{{ t(row.descriptionKey) }}</div>
              <n-space :size="6" class="card-caps">
                <n-tag v-for="c in row.capabilities" :key="c" size="small" :bordered="false">
                  {{ c }}
                </n-tag>
              </n-space>
              <div v-if="row.configured" class="card-meta">
                {{ t('providers.keys') }} ×{{ row.keyCount }} ·
                {{ t('providers.weight') }} {{ row.weight }} ·
                {{ t('providers.priority') }} {{ row.priority }}
              </div>
              <n-space :size="6" class="card-actions">
                <template v-if="row.configured">
                  <n-button size="small" type="primary" ghost @click="router.push(`/providers/${row.id}`)">
                    {{ t('providers.view') }}
                  </n-button>
                  <n-button size="small" type="error" ghost @click="onDelete(row)">
                    {{ t('providers.delete') }}
                  </n-button>
                </template>
                <template v-else>
                  <n-button size="small" type="primary" @click="router.push({ name: 'provider-new', params: { type: row.type } })">
                    {{ t('providers.add') }}
                  </n-button>
                </template>
              </n-space>
            </n-card>
          </n-grid-item>
        </n-grid>
      </template>
      <n-data-table v-else :columns="columns" :data="rows" :row-key="rowKey" size="small" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref, watch } from 'vue'
import type { PropType } from 'vue'
import { useDialog, useMessage, NButton, NSpace, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { adminApi, type ProviderCfg, type ProviderStatus } from '@/api/admin'
import { useProviderTypesStore } from '@/stores/providerTypes'
import { buildProviderRows, type ProviderRow } from '@/utils/providerRows'
import { t } from '@/i18n'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const typesStore = useProviderTypesStore()
const loading = ref(false)
const providers = ref<ProviderCfg[]>([])
const keyCounts = ref<Record<string, number>>({})
const configStatus = ref<Record<string, ProviderStatus>>({})
const viewMode = ref<'card' | 'table'>(localStorage.getItem('providers.viewMode') === 'table' ? 'table' : 'card')
watch(viewMode, (v) => localStorage.setItem('providers.viewMode', v))

const rows = computed<ProviderRow[]>(() =>
  buildProviderRows(typesStore.types, providers.value, keyCounts.value, configStatus.value),
)

const rowKey = (row: ProviderRow) => row.id

type StatusTagType = 'success' | 'error' | 'default'

function statusInfo(status: ProviderStatus | undefined, configured: boolean): { type: StatusTagType; text: string } {
  if (!configured) return { type: 'default', text: t('providers.unconfigured') }
  if (!status) return { type: 'default', text: t('providers.testNever') }
  const map: Record<string, [StatusTagType, string]> = {
    ok: ['success', t('providers.testOkShort')],
    failed: ['error', t('providers.testFailShort')],
    untested: ['default', t('providers.testNever')],
    missing_key: ['error', t('providers.missingKey')],
    missing_base_url: ['error', t('providers.missingBaseUrl')],
  }
  const [type, text] = map[status.status] ?? ['default', status.status]
  return { type, text }
}

const StatusTag = defineComponent({
  props: {
    status: { type: Object as PropType<ProviderStatus | undefined>, default: undefined },
    configured: { type: Boolean, required: true },
  },
  setup(props) {
    return () => {
      const { type, text } = statusInfo(props.status, props.configured)
      return h(NTag, { size: 'small', type }, { default: () => text })
    }
  },
})

const columns = computed<DataTableColumns<ProviderRow>>(() => [
  {
    title: t('providers.name'),
    key: 'name',
    render: (row) => h('span', { class: 'provider-name' }, row.name),
  },
  {
    title: t('providers.id'),
    key: 'id',
    render: (row) => (row.configured ? row.id : '—'),
  },
  {
    title: t('providers.type'),
    key: 'type',
    render: (row) => row.type,
  },
  {
    title: t('providers.description'),
    key: 'description',
    render: (row) => (row.descriptionKey ? t(row.descriptionKey) : '—'),
  },
  {
    title: t('providers.availability'),
    key: 'availability',
    render: (row) => {
      const { type, text } = statusInfo(row.status, row.configured)
      return h(NTag, { size: 'small', type }, { default: () => text })
    },
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
  { title: t('providers.keys'), key: 'keys', render: (row) => (row.configured ? String(row.keyCount) : '—') },
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
                  { size: 'small', type: 'error', ghost: true, onClick: () => onDelete(row) },
                  { default: () => t('providers.delete') },
                ),
              ]
            : [
                h(
                  NButton,
                  { size: 'small', type: 'primary', onClick: () => router.push({ name: 'provider-new', params: { type: row.type } }) },
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

function onDelete(row: ProviderRow) {
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
.provider-card {
  height: 100%;
}
.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.card-heading {
  min-width: 0;
}
.card-name {
  font-size: 15px;
  font-weight: 600;
}
.card-instance {
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}
.card-desc {
  font-size: 13px;
  color: #666;
  margin-bottom: 10px;
}
.card-caps {
  margin-bottom: 10px;
}
.card-meta {
  font-size: 13px;
  color: #888;
  margin-bottom: 10px;
}
.card-actions {
  justify-content: flex-end;
}
.provider-name {
  font-weight: 600;
}
</style>
