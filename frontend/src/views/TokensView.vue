<template>
  <div>
    <div class="tokens-head">
      <h1 class="page-title">{{ t('tokens.title') }}</h1>
      <n-button type="primary" @click="showCreateModal = true">
        {{ t('tokens.new') }}
      </n-button>
    </div>

    <n-data-table :columns="columns" :data="tokens" :loading="loading" size="small" />

    <n-modal v-model:show="showCreateModal" preset="card" :title="t('tokens.new')" style="width: 420px">
      <n-form label-placement="top">
        <n-form-item :label="t('tokens.name')">
          <n-input v-model:value="newName" :placeholder="t('tokens.name')" @keyup.enter="onCreate" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreateModal = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="creating" @click="onCreate">{{ t('tokens.create') }}</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showResult"
      preset="card"
      :title="t('tokens.new')"
      style="width: 540px"
      @update:show="(v: boolean) => { if (!v) discardResult() }"
    >
      <n-alert type="success" :show-icon="true">
        <p>{{ t('tokens.tokenOnce') }}</p>
        <n-space align="center" class="token-result">
          <n-input :value="created?.token ?? ''" readonly />
          <n-button type="primary" ghost @click="onCopy">{{ t('tokens.copy') }}</n-button>
        </n-space>
      </n-alert>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useDialog, useMessage, NButton, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { adminApi, type TokenInfo } from '@/api/admin'
import { t } from '@/i18n'

const dialog = useDialog()
const message = useMessage()
const loading = ref(false)
const creating = ref(false)
const tokens = ref<TokenInfo[]>([])
const showCreateModal = ref(false)
const showResult = ref(false)
const newName = ref('')
const created = ref<{ name: string; token: string } | null>(null)

const columns = computed<DataTableColumns<TokenInfo>>(() => [
  { title: t('tokens.name'), key: 'name' },
  { title: t('tokens.id'), key: 'id', render: (row) => row.id.slice(0, 8) },
  { title: t('tokens.hashPrefix'), key: 'hash_prefix' },
  {
    title: t('tokens.createdAt'),
    key: 'created_at',
    render: (row) => new Date(row.created_at * 1000).toLocaleString(),
  },
  {
    title: t('tokens.revoked'),
    key: 'revoked',
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.revoked ? 'error' : 'success' },
        { default: () => t(row.revoked ? 'tokens.revokedYes' : 'tokens.revokedNo') },
      ),
  },
  {
    title: t('tokens.actions'),
    key: 'actions',
    render: (row) =>
      h(
        NButton,
        { size: 'small', type: 'error', ghost: true, onClick: () => onDelete(row) },
        { default: () => t('tokens.delete') },
      ),
  },
])

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const r = await adminApi.listTokens()
    tokens.value = r.tokens
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    loading.value = false
  }
}

async function onCreate() {
  const name = newName.value.trim()
  if (!name) return
  creating.value = true
  try {
    const r = await adminApi.createToken(name)
    created.value = { name: r.name, token: r.token }
    newName.value = ''
    showCreateModal.value = false
    showResult.value = true
    await load()
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    creating.value = false
  }
}

function discardResult() {
  showResult.value = false
  created.value = null
}

async function onCopy() {
  if (!created.value) return
  try {
    await navigator.clipboard.writeText(created.value.token)
    message.success(t('tokens.copied'))
  } catch {
    message.error(t('common.failed'))
  }
}

function onDelete(row: TokenInfo) {
  dialog.warning({
    title: t('tokens.delete'),
    content: t('tokens.deleteConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await adminApi.deleteToken(row.id)
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
.tokens-head {
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
.token-result {
  width: 100%;
}
</style>
