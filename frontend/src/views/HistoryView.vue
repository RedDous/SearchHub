<template>
  <div>
    <h1 class="page-title">{{ t('history.title') }}</h1>

    <n-card class="filter-card" :bordered="false">
      <n-space align="center" :size="12" wrap>
        <n-select
          v-model:value="filters.capability"
          :options="capabilityOptions"
          style="width: 140px"
        />
        <n-input v-model:value="filters.provider" :placeholder="t('history.provider')" style="width: 160px" clearable @keyup.enter="onSearch" />
        <n-input v-model:value="filters.token" :placeholder="t('history.token')" style="width: 160px" clearable @keyup.enter="onSearch" />
        <n-input v-model:value="filters.q" :placeholder="t('history.query')" style="width: 180px" clearable @keyup.enter="onSearch" />
        <n-select v-model:value="filters.range" :options="timePresets" style="width: 150px" />
        <n-button type="primary" @click="onSearch">{{ t('history.search') }}</n-button>
        <n-button @click="onReset">{{ t('history.reset') }}</n-button>
      </n-space>
    </n-card>

    <n-data-table
      remote
      :columns="columns"
      :data="rows"
      :loading="loading"
      :pagination="pagination"
      :row-key="(row: HistoryRow) => row.id"
      :empty="t('history.empty')"
      size="small"
      @update:page="onPage"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useMessage, NCode, NEllipsis, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { adminApi, type HistoryRow } from '@/api/admin'
import { t } from '@/i18n'

const message = useMessage()
const loading = ref(false)
const rows = ref<HistoryRow[]>([])
const page = ref(1)
const itemCount = ref(0)
const PAGE_SIZE = 20

const filters = reactive({
  capability: null as string | null,
  provider: '',
  token: '',
  q: '',
  range: 'all',
})

const capabilityOptions = computed(() => [
  { label: t('history.all'), value: null },
  { label: 'search', value: 'search' },
  { label: 'extract', value: 'extract' },
])

const timePresets = computed(() => [
  { label: t('history.lastHour'), value: '1h' },
  { label: t('history.last24h'), value: '24h' },
  { label: t('history.last7d'), value: '7d' },
  { label: t('history.allTime'), value: 'all' },
])

const pagination = computed(() => ({
  page: page.value,
  pageSize: PAGE_SIZE,
  itemCount: itemCount.value,
  showSizePicker: false,
}))

function resolveRange(v: string): { from_ts?: number; to_ts?: number } {
  if (v === 'all') return {}
  const hours = { '1h': 1, '24h': 24, '7d': 168 }[v] ?? 24
  return { from_ts: Math.floor(Date.now() / 1000) - hours * 3600 }
}

const columns = computed<DataTableColumns<HistoryRow>>(() => [
  {
    title: t('history.time'),
    key: 'ts',
    width: 160,
    render: (row) => new Date(row.ts * 1000).toLocaleString(),
  },
  {
    title: t('history.capability'),
    key: 'capability',
    width: 100,
    render: (row) => h(NTag, { size: 'small', type: 'info' }, { default: () => row.capability }),
  },
  {
    title: t('history.query'),
    key: 'query',
    render: (row) => h(NEllipsis, { style: 'max-width: 240px' }, { default: () => row.query }),
  },
  { title: t('history.provider'), key: 'providers' },
  {
    title: t('history.cacheHit'),
    key: 'cache_hit',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.cache_hit ? 'success' : 'default' },
        { default: () => t(row.cache_hit ? 'history.yes' : 'history.no') },
      ),
  },
  { title: t('history.tookMs'), key: 'took_ms', width: 90 },
  { title: t('history.resultCount'), key: 'result_count', width: 90 },
  {
    title: t('history.success'),
    key: 'success',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.success ? 'success' : 'error' },
        { default: () => t(row.success ? 'history.successYes' : 'history.successNo') },
      ),
  },
  { title: t('history.token'), key: 'token_name' },
  {
    type: 'expand',
    renderExpand: (row) =>
      h('div', { class: 'detail' }, [
        h('div', { class: 'detail-block' }, [
          h('div', { class: 'detail-label' }, t('history.params')),
          h(NCode, { value: row.params, wordWrap: true }),
        ]),
        ...(row.error
          ? [
              h('div', { class: 'detail-block' }, [
                h('div', { class: 'detail-label' }, t('history.error')),
                h('pre', { class: 'detail-error' }, row.error),
              ]),
            ]
          : []),
        ...(row.response_preview
          ? [
              h('div', { class: 'detail-block' }, [
                h('div', { class: 'detail-label' }, t('history.preview')),
                h(NCode, { value: row.response_preview, wordWrap: true }),
              ]),
            ]
          : []),
      ]),
  },
])

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const { from_ts, to_ts } = resolveRange(filters.range)
    const r = await adminApi.listHistory({
      capability: filters.capability ?? undefined,
      provider: filters.provider.trim() || undefined,
      token: filters.token.trim() || undefined,
      q: filters.q.trim() || undefined,
      from_ts,
      to_ts,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    rows.value = r.rows
    itemCount.value = (page.value - 1) * PAGE_SIZE + r.rows.length
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}

function onReset() {
  filters.capability = null
  filters.provider = ''
  filters.token = ''
  filters.q = ''
  filters.range = 'all'
  page.value = 1
  load()
}

function onPage(p: number) {
  page.value = p
  load()
}

onMounted(load)
</script>

<style scoped>
.page-title {
  margin: 0 0 16px;
  font-size: 20px;
  font-weight: 600;
}
.filter-card {
  margin-bottom: 16px;
}
.detail {
  padding: 8px 16px;
}
.detail-block {
  margin-bottom: 12px;
}
.detail-label {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--n-text-color-3, #999);
}
.detail-error {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: #d03050;
}
</style>
