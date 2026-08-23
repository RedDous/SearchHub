<template>
  <div class="dashboard">
    <div class="dashboard-head">
      <h1 class="page-title">{{ t('dashboard.title') }}</h1>
      <n-space align="center">
        <span class="version-line">v{{ version }} · {{ commit }}</span>
        <n-button type="primary" :loading="loading" @click="load">
          {{ t('dashboard.refresh') }}
        </n-button>
      </n-space>
    </div>

    <n-grid :cols="4" :x-gap="12" :y-gap="12" class="stat-grid">
      <n-grid-item>
        <n-card :title="t('dashboard.totalRequests')" size="small">
          <n-statistic :value="fmt(summary?.total)"><template #suffix></template></n-statistic>
          <div v-if="noData" class="no-data-hint">{{ t('dashboard.noData') }}</div>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card :title="t('dashboard.successRate')" size="small">
          <n-statistic :value="pct(summary?.success_rate)"><template #suffix>%</template></n-statistic>
          <div v-if="noData" class="no-data-hint">{{ t('dashboard.noData') }}</div>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card :title="t('dashboard.cacheHitRate')" size="small">
          <n-statistic :value="pct(summary?.cache_hit_rate)"><template #suffix>%</template></n-statistic>
          <div v-if="noData" class="no-data-hint">{{ t('dashboard.noData') }}</div>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card :title="t('dashboard.avgLatency')" size="small">
          <n-statistic :value="ms(summary?.avg_took_ms)"><template #suffix>ms</template></n-statistic>
          <div v-if="noData" class="no-data-hint">{{ t('dashboard.noData') }}</div>
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-card :title="t('dashboard.requests24h')" size="small" class="chart-card">
      <BaseChart v-if="chartRows.length" :option="chartOption" height="320px" />
      <div v-else class="no-data">{{ t('dashboard.noData') }}</div>
    </n-card>

    <n-card :title="t('dashboard.providers')" size="small">
      <n-data-table :columns="providerColumns" :data="providerRows" :loading="loading" size="small" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useMessage, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import type { EChartsOption } from 'echarts'
import { adminApi, type StatsSummary } from '@/api/admin'
import BaseChart from '@/components/BaseChart.vue'
import { t } from '@/i18n'

interface ProviderStatusRow {
  id: string
  capabilities: string[]
  weight: number
  priority: number
  keys: unknown[]
  stats?: { calls: number; errors: number; avg_ms: number }
}

interface ChartRow {
  time: string
  count: number
  cached: number
}

const message = useMessage()
const loading = ref(false)
const version = ref('-')
const commit = ref('-')
const summary = ref<StatsSummary | null>(null)
const chartRows = ref<ChartRow[]>([])

const noData = computed(() => !summary.value || summary.value.total === 0)

function fmt(v: number | undefined): string {
  return String(v ?? 0)
}

function pct(v: number | undefined): string {
  if (noData.value) return '-'
  return ((v ?? 0) * 100).toFixed(1)
}

function ms(v: number | undefined): string {
  if (noData.value) return '-'
  return String(v ?? 0)
}

const chartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: [t('dashboard.totalRequests'), t('dashboard.cacheHitRate')], bottom: 4 },
  grid: { left: 8, right: 8, top: 24, bottom: 32, containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: chartRows.value.map((r) => r.time),
  },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    {
      name: t('dashboard.totalRequests'),
      type: 'line',
      smooth: true,
      showSymbol: false,
      areaStyle: {},
      data: chartRows.value.map((r) => r.count),
    },
    {
      name: t('dashboard.cacheHitRate'),
      type: 'line',
      smooth: true,
      showSymbol: false,
      areaStyle: {},
      data: chartRows.value.map((r) => r.cached),
    },
  ],
}))

const providerColumns = computed<DataTableColumns<ProviderStatusRow>>(() => [
  { title: t('dashboard.id'), key: 'id' },
  {
    title: t('dashboard.capabilities'),
    key: 'capabilities',
    render: (row) =>
      h(
        'span',
        row.capabilities.map((c) => h(NTag, { size: 'small', style: 'margin-right: 6px' }, { default: () => c })),
      ),
  },
  { title: t('dashboard.weight'), key: 'weight' },
  { title: t('dashboard.priority'), key: 'priority' },
  { title: t('dashboard.calls'), key: 'calls', render: (row) => (row.stats ? String(row.stats.calls) : '-') },
  { title: t('dashboard.errors'), key: 'errors', render: (row) => (row.stats ? String(row.stats.errors) : '-') },
  { title: t('dashboard.avgMs'), key: 'avg_ms', render: (row) => (row.stats ? String(row.stats.avg_ms) : '-') },
  { title: t('dashboard.keys'), key: 'keys', render: (row) => String(row.keys?.length ?? 0) },
])

const providerRows = computed<ProviderStatusRow[]>(() => (summary.value?.providers ?? []) as unknown as ProviderStatusRow[])

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const [cfg, s, ts] = await Promise.all([
      adminApi.getConfig(),
      adminApi.getStatsSummary(24),
      adminApi.getStatsTimeseries(24),
    ])
    version.value = cfg.version
    commit.value = cfg.commit.slice(0, 7)
    summary.value = s
    chartRows.value = ts.rows.map((r) => ({
      time: new Date(r.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      count: r.count,
      cached: r.cache_hits,
    }))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.dashboard-head {
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
.stat-grid {
  margin-bottom: 12px;
}
.chart-card {
  margin-bottom: 12px;
}
.no-data {
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color-3, #999);
}
.no-data-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--n-text-color-3, #999);
}
</style>
