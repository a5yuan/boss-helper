<script setup lang="ts">
/**
 * ChipGroup：通用 chip 多选组。
 * v-model 为字符串数组；点击 chip 切换其是否在数组里。
 * 内部用 GlassTag 渲染，保持与 UI 设计系统一致。
 */
defineProps<{
  modelValue: string[];
  options: string[];
  label?: string;
  emptyHint?: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: string[]): void;
}>();

function toggle(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}
</script>

<template>
  <div v-if="options.length || emptyHint" class="flex items-center gap-1.5 min-w-0">
    <span v-if="label" class="text-[11px] text-fg-subtle shrink-0">{{ label }}</span>
    <div class="flex flex-wrap gap-1 min-w-0">
      <button
        v-for="o in options"
        :key="o"
        type="button"
        class="chip"
        :class="{ 'is-on': modelValue.includes(o) }"
        :title="`仅显示包含「${o}」的岗位`"
        @click="emit('update:modelValue', toggle(modelValue, o))"
      >{{ o }}</button>
      <span v-if="!options.length && emptyHint" class="text-[11px] text-fg-subtle italic">
        {{ emptyHint }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.chip {
  font-size: 11px;
  padding: 0.18rem 0.6rem;
  border-radius: var(--radius-pill, 999px);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--fg-muted);
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
  white-space: nowrap;
  line-height: 1.5;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.chip:hover {
  border-color: var(--glass-border-hover);
  color: var(--fg);
  background: var(--glass-bg-hover);
}
.chip.is-on {
  background: var(--accent);
  border-color: transparent;
  color: var(--accent-fg);
}
</style>