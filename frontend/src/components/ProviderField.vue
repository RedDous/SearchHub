<template>
  <n-form-item
    :label="t(field.label)"
    :feedback="field.help ? t(field.help) : undefined"
    :required="field.required"
  >
    <n-input
      v-if="field.type === 'string'"
      :value="stringValue"
      :placeholder="field.placeholder || undefined"
      clearable
      @update:value="onString"
    />
    <n-input
      v-else-if="field.type === 'text'"
      :value="stringValue"
      type="textarea"
      :rows="3"
      :placeholder="field.placeholder || undefined"
      @update:value="onString"
    />
    <n-input-number
      v-else-if="field.type === 'int'"
      :value="numberValue"
      :min="field.min ?? undefined"
      :max="field.max ?? undefined"
      :step="field.step ?? 1"
      :precision="0"
      style="width: 160px"
      @update:value="onNumber"
    />
    <n-input-number
      v-else-if="field.type === 'float'"
      :value="numberValue"
      :min="field.min ?? undefined"
      :max="field.max ?? undefined"
      :step="field.step ?? 0.1"
      style="width: 160px"
      @update:value="onNumber"
    />
    <n-switch v-else-if="field.type === 'bool'" :value="boolValue" @update:value="onBool" />
    <n-select
      v-else-if="field.type === 'enum'"
      :value="enumValue"
      :options="choiceOptions"
      :placeholder="field.placeholder || undefined"
      style="max-width: 320px"
      @update:value="onEnum"
    />
    <n-dynamic-tags
      v-else-if="field.type === 'string_list'"
      :value="listValue"
      style="max-width: 480px"
      @update:value="onList"
    />
    <n-input
      v-else-if="field.type === 'secret'"
      :value="stringValue"
      type="password"
      show-password-on="click"
      :placeholder="field.placeholder || undefined"
      @update:value="onString"
    />
    <!-- Unknown future field types fall back to a plain text input. -->
    <n-input
      v-else
      :value="stringValue"
      :placeholder="field.placeholder || undefined"
      @update:value="onString"
    />
  </n-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FieldSpec } from '@/api/admin'
import { t } from '@/i18n'

const props = defineProps<{ field: FieldSpec; modelValue: unknown }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: unknown): void }>()

const stringValue = computed(() => (props.modelValue == null ? '' : String(props.modelValue)))
const numberValue = computed(() => (typeof props.modelValue === 'number' ? props.modelValue : null))
const boolValue = computed(() => props.modelValue === true)
const enumValue = computed(() => (props.modelValue == null ? null : String(props.modelValue)))
const listValue = computed<string[]>(() =>
  Array.isArray(props.modelValue) ? props.modelValue.filter((v): v is string => typeof v === 'string') : [],
)
const choiceOptions = computed(() =>
  (props.field.choices ?? []).map((choice) => ({
    label: choice === '' ? t('providers.fields.none') : choice,
    value: choice,
  })),
)

function onString(value: string) {
  emit('update:modelValue', value)
}
function onNumber(value: number | null) {
  emit('update:modelValue', value)
}
function onBool(value: boolean) {
  emit('update:modelValue', value)
}
function onEnum(value: string) {
  emit('update:modelValue', value)
}
function onList(value: string[]) {
  emit('update:modelValue', [...value])
}
</script>
