<template>
  <n-modal
    :show="open"
    preset="card"
    :title="t('setup.forceChangeTitle')"
    :mask-closable="false"
    :close-on-esc="false"
    :closable="false"
    style="width: 420px"
    @update:show="onUpdateShow"
  >
    <p class="force-desc">{{ t('setup.forceChangeDesc') }}</p>
    <n-form label-placement="left" label-width="110" @submit.prevent="submit">
      <n-form-item :label="t('system.oldPassword')">
        <n-input v-model:value="oldPassword" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item :label="t('system.newPassword')">
        <n-input v-model:value="newPassword" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item :label="t('system.confirmPassword')">
        <n-input v-model:value="confirmPassword" type="password" show-password-on="click" @keyup.enter="submit" />
      </n-form-item>
      <n-space justify="end">
        <n-button :disabled="submitting" @click="onCancel">{{ t('common.cancel') }}</n-button>
        <n-button type="primary" :loading="submitting" @click="submit">{{ t('common.confirm') }}</n-button>
      </n-space>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { t } from '@/i18n'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'changed'): void }>()
const auth = useAuthStore()
const message = useMessage()
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)

function onUpdateShow(v: boolean) {
  emit('update:open', v)
}

function onCancel() {
  if (submitting.value) return
  emit('update:open', false)
}

async function submit() {
  if (submitting.value) return
  if (newPassword.value.length < 8) {
    message.error(t('system.passwordTooShort'))
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    message.error(t('system.passwordMismatch'))
    return
  }
  submitting.value = true
  try {
    await auth.changePassword(oldPassword.value, newPassword.value)
    message.success(t('system.passwordChanged'))
    oldPassword.value = newPassword.value = confirmPassword.value = ''
    emit('update:open', false)
    emit('changed')
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.force-desc {
  margin: 0 0 16px;
  color: #888;
  font-size: 13px;
}
</style>
