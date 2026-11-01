<template>
  <div class="provider-options">
    <template v-for="(group, name) in basicGroups" :key="name">
      <div class="options-group-title">{{ groupLabel(String(name)) }}</div>
      <ProviderField
        v-for="field in group"
        :key="field.key"
        :field="field"
        :model-value="options[field.key]"
        @update:model-value="(value) => update(field.key, value)"
      />
    </template>

    <n-collapse v-if="advancedFields.length" class="options-advanced">
      <n-collapse-item :title="t('providers.fields.advanced')" name="advanced">
        <ProviderField
          v-for="field in advancedFields"
          :key="field.key"
          :field="field"
          :model-value="options[field.key]"
          @update:model-value="(value) => update(field.key, value)"
        />
      </n-collapse-item>
    </n-collapse>

    <div v-if="!hasVisibleFields" class="options-empty">{{ t('providers.fields.empty') }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FieldSpec } from '@/api/admin'
import { groupFields, isFieldVisible } from '@/utils/providerFields'
import { t } from '@/i18n'
import ProviderField from '@/components/ProviderField.vue'

const props = defineProps<{
  fields: FieldSpec[]
  options: Record<string, unknown>
  capabilities: string[]
}>()
const emit = defineEmits<{ (e: 'update:options', value: Record<string, unknown>): void }>()

/** Fields that apply to at least one of the selected capabilities. */
const applicableFields = computed(() =>
  props.fields.filter(
    (field) => !field.capability || props.capabilities.includes(field.capability),
  ),
)

/** Fields whose `visible_when` conditions currently match. */
const visibleFields = computed(() =>
  applicableFields.value.filter((field) => isFieldVisible(field, props.options)),
)

const basicFields = computed(() => visibleFields.value.filter((field) => !field.advanced))
const advancedFields = computed(() => visibleFields.value.filter((field) => field.advanced))
const basicGroups = computed(() => groupFields(basicFields.value))
const hasVisibleFields = computed(
  () => basicFields.value.length > 0 || advancedFields.value.length > 0,
)

function groupLabel(group: string): string {
  const key = `providers.fields.groups.${group}`
  const label = t(key)
  return label === key ? group : label
}

function update(key: string, value: unknown) {
  emit('update:options', { ...props.options, [key]: value })
}
</script>

<style scoped>
.options-group-title {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin: 4px 0 8px;
}
.options-group-title:not(:first-child) {
  margin-top: 16px;
}
.options-advanced {
  margin-top: 12px;
}
.options-empty {
  font-size: 13px;
  color: #888;
}
</style>
