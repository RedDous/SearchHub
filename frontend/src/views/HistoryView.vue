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
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { useMessage, NCode, NEllipsis, NTag } from 'naive-ui'
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
const expandedFull = ref<Record<number, boolean>>({})
const itemOpen = ref<Record<string, boolean>>({})

function toggleItem(id: number, i: number) {
  const key = `${id}:${i}`
  itemOpen.value[key] = !itemOpen.value[key]
}

async function toggleFull(row: HistoryRow) {
  const id = row.id
  if (fullLoading.value[id]) return
  if (expandedFull.value[id]) {
    expandedFull.value[id] = false
    return
  }
  expandedFull.value[id] = true
  if (fullMap.value[id]) return
  fullLoading.value[id] = true
  try {
    const r = await adminApi.getHistoryFull(id)
    const parsed = JSON.parse(r.response_full) as { items?: HistoryFullEntry[] }
    fullMap.value[id] = parsed.items ?? []
  } catch (e) {
    fullMap.value[id] = null
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    fullLoading.value[id] = false
  }
}

const HistoryExpand = defineComponent({
  props: { row: { type: Object as PropType<HistoryRow>, required: true } },
  setup(props) {
    return () => {
      const row = props.row
      const id = row.id
      const entries = fullMap.value[id]
      const loading = fullLoading.value[id]
      const open = expandedFull.value[id]
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
      const hint = loading
        ? t('history.loadingFull')
        : open
          ? t('history.collapseFull')
          : t('history.expandFull')
      const title = open ? t('history.fullResponse') : t('history.preview')
      const renderItem = (it: HistoryFullEntry, i: number) => {
        const isSearch = row.capability === 'search'
        const openKey = `${id}:${i}`
        const opened = !!itemOpen.value[openKey]
        const head = isSearch
          ? h('a', { class: 'full-item-head-text', href: it.url, target: '_blank', rel: 'noopener' }, `${i + 1}. ${it.title ?? it.url}`)
          : h('span', { class: 'full-item-head-text' }, it.url)
        const body = isSearch
          ? [
              h('div', { class: 'full-item-url' }, it.url),
              it.description ? h('div', { class: 'full-item-desc' }, it.description) : null,
            ]
          : [
              it.title ? h('div', { class: 'full-item-desc' }, it.title) : null,
              it.error
                ? h('div', { class: 'full-item-desc full-item-error-text' }, it.error)
                : h('pre', { class: 'full-item-content' }, it.content ?? ''),
            ]
        if (it.provider) body.push(h('span', { class: 'full-item-provider' }, it.provider))
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
          h(
            'div',
            {
              class: ['detail-title', { 'detail-title-clickable': !!row.has_full }],
              onClick: row.has_full ? () => toggleFull(row) : undefined,
            },
            [
              h('span', {}, title),
              row.has_full ? h('span', { class: 'detail-title-hint' }, hint) : null,
              row.has_full ? h('span', { class: ['caret', { open }] }, '▸') : null,
            ],
          ),
          open
            ? loading
              ? h('div', { class: 'detail-content' }, [h('span', { class: 'loading-text' }, t('history.loadingFull'))])
              : h('div', { class: ['full-collapse', { open: true }] }, [
                  h('div', { class: 'full-collapse-inner' }, [
                    h('div', { class: 'detail-block full-block' }, [
                      h('div', { class: 'full-list' }, (entries ?? []).map(renderItem)),
                    ]),
                  ]),
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
    render: (row) => h(NEllipsis, { style: 'max-width: 240px' }, { default: () => row.query }),
  },
  { title: t('history.provider'), key: 'providers' },
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
.detail-title-clickable {
  cursor: pointer;
  user-select: none;
}
.detail-title-clickable:hover {
  color: #2080f0;
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
.detail-title-hint {
  margin-left: auto;
  font-size: 12px;
  font-weight: 400;
  color: var(--n-text-color-3, #999);
}
.full-collapse {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.28s ease;
}
.full-collapse.open {
  grid-template-rows: 1fr;
}
.full-collapse-inner {
  overflow: hidden;
  min-height: 0;
}
.full-block {
  margin-top: 12px;
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
a.full-item-head-text:hover {
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
.full-item-provider {
  display: inline-block;
  margin-top: 4px;
  font-size: 11px;
  color: #888;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  padding: 1px 6px;
}
</style>
