<!-- GlassCheckbox — 毛玻璃选中框（v-model:boolean） -->
<script setup lang="ts">
const props = withDefaults(
  defineProps<{ modelValue?: boolean; disabled?: boolean }>(),
  { modelValue: false, disabled: false }
);
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();
function toggle() {
  if (!props.disabled) emit("update:modelValue", !props.modelValue);
}
</script>

<template>
  <button
    type="button"
    class="gcheck"
    :class="{ 'is-on': modelValue }"
    role="checkbox"
    :aria-checked="modelValue"
    :disabled="disabled"
    @click="toggle"
  >
    <svg
      v-if="modelValue"
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="3"
    >
      <path d="M5 12l5 5L20 7" />
    </svg>
  </button>
</template>

<style scoped>
.gcheck {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border: 1.5px solid rgba(17, 17, 19, 0.22);
  background: var(--glass-bg);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  color: var(--accent-fg);
  transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.gcheck:hover {
  border-color: rgba(17, 17, 19, 0.38);
  box-shadow: 0 0 0 2px rgba(17, 17, 19, 0.08);
}
.gcheck.is-on {
  background: var(--accent);
  border-color: var(--accent);
}
.gcheck:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
