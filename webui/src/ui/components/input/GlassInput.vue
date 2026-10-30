<!-- GlassInput — 毛玻璃输入框（v-model，支持 icon 插槽） -->
<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue?: string | number;
    placeholder?: string;
    type?: string;
  }>(),
  { type: "text", placeholder: "" }
);
defineEmits<{ (e: "update:modelValue", v: string): void }>();
</script>

<template>
  <div class="ginput">
    <span v-if="$slots.icon" class="ginput__icon"><slot name="icon" /></span>
    <input
      class="ginput__field"
      :type="type"
      :placeholder="placeholder"
      :value="modelValue ?? ''"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>

<style scoped>
.ginput {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.85rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.ginput:focus-within {
  border-color: var(--glass-border-hover);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.1);
}
.ginput__icon {
  color: var(--fg-subtle);
  display: inline-flex;
}
.ginput__field {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--fg);
  font-size: 0.875rem;
  padding: 0.6rem 0;
  width: 100%;
}
.ginput__field::placeholder {
  color: var(--fg-subtle);
}
</style>
