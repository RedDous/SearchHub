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
        <n-input v-model:value="filters.token" :placeholder="t('history.caller')" style="width: 160px" clearable @keyup.enter="onSearch" />
        <n-input v-model:value="filters.q" :placeholder="t('history.query')" style="width: 180px" clearable @keyup.enter="onSearch" />
        <n-select v-model:value="filters.range" :options="timePresets" style="width: 150px" />
        <n-button type="primary" @click="onSearch">{{ t('history.search') }}</n-button>
        <n-button @click="onReset">{{ t('history.reset') }}</n-button>
      </n-space>
    </n-card>

    <n-data-table
      remote
      class="history-table"
      :columns="columns"
      :data="rows"
      :loading="loading"
      :pagination="pagination"
      :row-key="(row: HistoryRow) => row.id"
      :expanded-row-keys="expandedRows"
      :row-props="(row: HistoryRow) => ({ onClick: () => toggleRowExpand(row), class: 'clickable-row' })"
      :empty="t('history.empty')"
      size="small"
      @update:expanded-row-keys="onExpandedChange"
      @update:page="onPage"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { useMessage, NCode, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import type { PropType } from 'vue'
import { adminApi, type HistoryFullEntry, type HistoryRow } from '@/api/admin'
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

const fullMap = ref<Record<number, HistoryFullEntry[] | null>>({})
const fullLoading = ref<Record<number, boolean>>({})
const itemOpen = ref<Record<string, boolean>>({})
const expandedRows = ref<number[]>([])

function toggleRowExpand(row: HistoryRow) {
  const i = expandedRows.value.indexOf(row.id)
  if (i >= 0) expandedRows.value.splice(i, 1)
  else expandedRows.value.push(row.id)
}

function onExpandedChange(keys: number[]) {
  expandedRows.value = keys
}

function toggleItem(id: number, i: number) {
  const key = `${id}:${i}`
  itemOpen.value[key] = !itemOpen.value[key]
}

async function ensureFull(row: HistoryRow) {
  const id = row.id
  if (fullLoading.value[id] || fullMap.value[id] !== undefined) return
  fullLoading.value[id] = true
  try {
    const r = await adminApi.getHistoryFull(id)
    const parsed = JSON.parse(r.response_full) as { items?: HistoryFullEntry[] }
    fullMap.value[id] = parsed.items ?? []
  } catch {
    fullMap.value[id] = null
  } finally {
    fullLoading.value[id] = false
  }
}

const HistoryExpand = defineComponent({
  props: { row: { type: Object as PropType<HistoryRow>, required: true } },
  setup(props) {
    onMounted(() => {
      if (props.row.has_full) ensureFull(props.row)
    })
    return () => {
      const row = props.row
      const id = row.id
      const entries = fullMap.value[id]
      const loading = fullLoading.value[id]
      const blocks = [
        h('div', { class: 'detail-block' }, [
          h('div', { class: 'detail-title' }, t('history.params')),
          h('div', { class: 'detail-content' }, [
            h(NCode, { code: row.params, wordWrap: true }),
          ]),
        ]),
      ]
      if (row.error) {
        blocks.push(
          h('div', { class: 'detail-block' }, [
            h('div', { class: 'detail-title detail-title-error' }, t('history.error')),
            h('div', { class: 'detail-content' }, [
              h('pre', { class: 'detail-error' }, row.error),
            ]),
          ]),
        )
      }
      const renderItem = (it: HistoryFullEntry, i: number) => {
        const isSearch = row.capability === 'search'
        const openKey = `${id}:${i}`
        const opened = !!itemOpen.value[openKey]
        const head = h(
          'span',
          { class: 'full-item-head-text' },
          isSearch ? `${i + 1}. ${it.title ?? it.url}` : it.url,
        )
        const chars = isSearch ? (it.description ?? '').length : (it.content ?? '').length
        const chartTag = h('span', { class: 'full-item-chars' }, `${chars} ${t('history.chars')}`)
        const urlLine = h('div', { class: 'full-item-url-line' }, [
          it.provider ? h('span', { class: 'full-item-provider' }, it.provider) : null,
          chartTag,
          isSearch
            ? h('a', { class: 'full-item-url', href: it.url, target: '_blank', rel: 'noopener' }, it.url)
            : h('span', { class: 'full-item-url' }, it.url),
        ])
        const body = isSearch
          ? [
              urlLine,
              it.description ? h('div', { class: 'full-item-desc' }, it.description) : null,
            ]
          : [
              urlLine,
              it.title ? h('div', { class: 'full-item-desc' }, it.title) : null,
              it.error
                ? h('div', { class: 'full-item-desc full-item-error-text' }, it.error)
                : h('pre', { class: 'full-item-content' }, it.content ?? ''),
            ]
        return h('div', { class: ['full-item', { 'full-item-error': !!it.error }] }, [
          h('div', { class: 'full-item-head', onClick: () => toggleItem(id, i) }, [
            head,
            h('span', { class: ['caret', { open: opened }] }, '▸'),
          ]),
          opened ? h('div', { class: 'full-item-body' }, body) : null,
        ])
      }
      blocks.push(
        h('div', { class: 'detail-block' }, [
          h('div', { class: 'detail-title' }, t('history.response')),
          row.has_full
            ? loading
              ? h('div', { class: 'detail-content' }, [h('span', { class: 'loading-text' }, t('history.loadingFull'))])
              : entries === null
                ? h('div', { class: 'detail-content' }, [h('span', { class: 'loading-text' }, t('common.failed'))])
                : h('div', { class: 'detail-content' }, [
                    h('div', { class: 'full-list' }, entries.map(renderItem)),
                  ])
            : h('div', { class: 'detail-content' }, [
                h(NCode, { code: row.response_preview, wordWrap: true }),
              ]),
        ]),
      )
      return h('div', { class: 'detail' }, blocks)
    }
  },
})

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
    minWidth: 200,
    ellipsis: { tooltip: true },
  },
  {
    title: t('history.provider'),
    key: 'providers',
    render: (row) =>
      h(
        'div',
        { class: 'providers-tags' },
        (row.providers || '').split(',').filter(Boolean).map((p) =>
          h(NTag, { size: 'small', bordered: false }, { default: () => p }),
        ),
      ),
  },
  {
    title: t('history.caller'),
    key: 'token_name',
    width: 120,
    render: (row) => row.token_name || '—',
  },
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
  {
    title: t('history.tookMs'),
    key: 'took_ms',
    width: 90,
    render: (row) => `${Math.round(row.took_ms)} ms`,
  },
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
  {
    type: 'expand',
    width: 40,
    renderExpand: (row) => h(HistoryExpand, { row }),
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
    itemCount.value =
      (page.value - 1) * PAGE_SIZE + r.rows.length + (r.rows.length === PAGE_SIZE ? 1 : 0)
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
</style>

<style>
.detail {
  padding: 12px 16px 4px;
}
.detail-block {
  margin-bottom: 16px;
}
.detail-block + .detail-block {
  border-top: 1px dashed var(--n-border-color, #dcdce0);
  padding-top: 14px;
}
.detail-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color-1, #1f1f1f);
  border-left: 3px solid #2080f0;
  padding-left: 8px;
  margin-bottom: 8px;
}
.detail-title-error {
  border-left-color: #d03050;
  color: #d03050;
}
.caret {
  display: inline-block;
  font-size: 11px;
  color: #888;
  transition: transform 0.25s ease;
}
.caret.open {
  transform: rotate(90deg);
}
.detail-content {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
  background: var(--n-color-2, #fafafa);
  padding: 8px 12px;
}
.loading-text {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
}
.detail-error {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: #d03050;
  font-size: 12px;
}
.full-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.full-item {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
}
.full-item-error {
  border-color: #f0c9c9;
  background: #fdf3f3;
}
.full-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  user-select: none;
}
.full-item-head .caret {
  margin-left: auto;
}
.full-item-head:hover {
  background: rgba(0, 0, 0, 0.02);
}
.full-item-head-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color-1, #1f1f1f);
  text-decoration: none;
  word-break: break-all;
}
.full-item-url {
  font-size: 12px;
  color: #2080f0;
  word-break: break-all;
  margin-top: 2px;
  text-decoration: none;
}
.full-item-url:hover {
  text-decoration: underline;
}
.full-item-body {
  padding: 0 10px 10px 28px;
}
.full-item-url {
  font-size: 12px;
  color: #2080f0;
  word-break: break-all;
  margin-top: 2px;
}
.full-item-desc {
  font-size: 12px;
  color: var(--n-text-color-3, #888);
  margin-top: 2px;
  word-break: break-all;
}
.full-item-content {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--n-text-color-2, #333);
}
.full-item-error-text {
  color: #d03050;
}
.full-item-url-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.full-item-provider {
  display: inline-block;
  font-size: 11px;
  color: #888;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.full-item-chars {
  display: inline-block;
  font-size: 11px;
  color: #888;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  padding: 1px 6px;
  flex-shrink: 0;
  white-space: nowrap;
}

/* ---- 深色模式 ---- */
.dark .detail-title {
  color: #e8e8e8;
}
.dark .caret {
  color: #9a9a9a;
}
.dark .detail-content {
  border-color: #3a3a40;
  background: #262626;
}
.dark .detail-error {
  color: #e88080;
}
.dark .full-item {
  border-color: #3a3a40;
}
.dark .full-item-head:hover {
  background: rgba(255, 255, 255, 0.05);
}
.dark .full-item-head-text {
  color: #e8e8e8;
}
.dark .full-item-url {
  color: #70c0e8;
}
.dark .full-item-desc {
  color: #a0a0a0;
}
.dark .full-item-content {
  color: #c8c8c8;
}
.dark .full-item-provider,
.dark .full-item-chars {
  color: #a0a0a0;
  background: rgba(255, 255, 255, 0.08);
}
.dark .full-item-error {
  border-color: #4a2c31;
  background: #2a1e21;
}
.dark .full-item-error-text {
  color: #e88080;
}
.dark .loading-text {
  color: #8f8f8f;
}
.clickable-row {
  cursor: pointer;
}
.providers-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.providers-tags .n-tag {
  white-space: nowrap;
}
</style>
