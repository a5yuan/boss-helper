<!-- GlassToggle — 毛玻璃开关（v-model:boolean） -->
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
    class="gtoggle"
    :class="{ 'is-on': modelValue }"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    type="button"
    @click="toggle"
  >
    <span class="gtoggle__knob" />
  </button>
</template>

<style scoped>
.gtoggle {
  position: relative;
  width: 46px;
  height: 26px;
  padding: 0;
  border-radius: var(--radius-pill);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.gtoggle__knob {
  position: absolute;
  top: 50%;
  left: 3px;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  border-radius: 50%;
  /* 关态：旋钮用前景色，与玻璃底（浅色=浅、深色=深）形成对比，避免「全黑」看不见 */
  background: var(--fg);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  transition: left var(--dur) var(--ease), background var(--dur) var(--ease);
}
.is-on {
  background: var(--accent);
  border-color: transparent;
}
.is-on .gtoggle__knob {
  left: 25px;
  /* 开态：底色=accent，旋钮用 accent-fg 成对反转（浅色=黑底白钮，深色=白底黑钮） */
  background: var(--accent-fg);
}
.gtoggle:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
