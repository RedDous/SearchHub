<template>
  <div class="login-wrap">
    <n-card class="login-card" :title="t('login.title')">
      <n-form @submit.prevent="submit">
        <n-form-item :label="t('login.username')">
          <n-input v-model:value="username" />
        </n-form-item>
        <n-form-item :label="t('login.password')">
          <n-input v-model:value="password" type="password" @keydown.enter="submit" />
        </n-form-item>
        <n-button type="primary" block :loading="loading" attr-type="submit">
          {{ t('login.submit') }}
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { onUnauthorized, setOnUnauthorized } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { t } from '@/i18n'

const router = useRouter()
const auth = useAuthStore()
const message = useMessage()
const username = ref('admin')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (loading.value) return
  loading.value = true
  const original = onUnauthorized
  setOnUnauthorized(() => {})
  try {
    await auth.login(username.value, password.value)
    let isDefault = false
    try {
      isDefault = await auth.isDefaultPassword()
    } catch {
      isDefault = false
    }
    if (isDefault) {
      router.push({ name: 'system' })
      await nextTick()
    } else {
      router.push({ name: 'dashboard' })
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('login.error'))
  } finally {
    setOnUnauthorized(original)
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--sh-wallpaper, #f5f7fa);
  background-size: cover;
  background-position: center;
}
.login-card {
  width: 360px;
}
.login-wrap :deep(.login-card) {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(14px) saturate(1.5);
}
.dark .login-wrap :deep(.login-card) {
  background: rgba(18, 22, 30, 0.72);
}
</style>
