import { computed, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { enUS, zhCN, type NLocale } from 'naive-ui'

export type Lang = 'zh' | 'en'

export const messages: Record<Lang, Record<string, string>> = {
  zh: {
    'login.title': 'SearchHub 管理后台',
    'login.username': '用户名',
    'login.password': '密码',
    'login.submit': '登 录',
    'login.error': '用户名或密码错误',
    'common.save': '保存',
    'common.cancel': '取消',
    'common.delete': '删除',
    'common.confirm': '确定',
    'common.success': '操作成功',
    'common.failed': '操作失败',
    'common.loading': '加载中…',
    'common.refresh': '刷新',
    'nav.dashboard': '仪表盘',
    'nav.providers': '供应商',
    'nav.settings': '策略与缓存',
    'nav.tokens': '调用方 Token',
    'nav.history': '历史查询',
    'nav.system': '系统设置',
    'nav.logout': '退出登录',
    'dashboard.title': '仪表盘',
    'dashboard.totalRequests': '24 小时请求数',
    'dashboard.successRate': '成功率',
    'dashboard.cacheHitRate': '缓存命中率',
    'dashboard.avgLatency': '平均耗时',
    'dashboard.requests24h': '近 24 小时请求趋势',
    'dashboard.providers': '供应商状态',
    'dashboard.refresh': '刷新',
    'dashboard.id': 'ID',
    'dashboard.capabilities': '能力',
    'dashboard.weight': '权重',
    'dashboard.priority': '优先级',
    'dashboard.calls': '调用数',
    'dashboard.errors': '错误数',
    'dashboard.avgMs': '平均耗时(ms)',
    'dashboard.keys': 'Key 数',
    'dashboard.noData': '暂无数据',
  },
  en: {
    'login.title': 'SearchHub Admin',
    'login.username': 'Username',
    'login.password': 'Password',
    'login.submit': 'Sign in',
    'login.error': 'Invalid username or password',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.delete': 'Delete',
    'common.confirm': 'OK',
    'common.success': 'Success',
    'common.failed': 'Failed',
    'common.loading': 'Loading…',
    'common.refresh': 'Refresh',
    'nav.dashboard': 'Dashboard',
    'nav.providers': 'Providers',
    'nav.settings': 'Strategy & Cache',
    'nav.tokens': 'API Tokens',
    'nav.history': 'History',
    'nav.system': 'Settings',
    'nav.logout': 'Sign out',
    'dashboard.title': 'Dashboard',
    'dashboard.totalRequests': 'Requests (24h)',
    'dashboard.successRate': 'Success rate',
    'dashboard.cacheHitRate': 'Cache hit rate',
    'dashboard.avgLatency': 'Avg latency',
    'dashboard.requests24h': 'Requests (last 24h)',
    'dashboard.providers': 'Providers',
    'dashboard.refresh': 'Refresh',
    'dashboard.id': 'ID',
    'dashboard.capabilities': 'Capabilities',
    'dashboard.weight': 'Weight',
    'dashboard.priority': 'Priority',
    'dashboard.calls': 'Calls',
    'dashboard.errors': 'Errors',
    'dashboard.avgMs': 'Avg ms',
    'dashboard.keys': 'Keys',
    'dashboard.noData': 'No data',
  },
}

const saved = (localStorage.getItem('sh_lang') as Lang) || 'zh'
export const lang: Ref<Lang> = ref(saved)
export const naiveLocale: ComputedRef<NLocale> = computed(() => (lang.value === 'zh' ? zhCN : enUS))

export function t(key: string, l: Lang = lang.value): string {
  return messages[l][key] ?? key
}

export function setLang(l: Lang): void {
  lang.value = l
  localStorage.setItem('sh_lang', l)
}
