<!-- GlassSelect — 自定义毛玻璃下拉选择，完全可控的选中/悬停态 -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { tracer } from "@/utils/tracer";

interface Opt {
  label: string;
  value: string;
}

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    options?: Opt[];
    placeholder?: string;
    disabled?: boolean;
    filterable?: boolean;
  }>(),
  { options: () => [], placeholder: "请选择", filterable: false }
);
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

const open = ref(false);
const filter = ref("");
const searchInput = ref<HTMLInputElement | null>(null);
const current = computed(() => props.options.find((o) => o.value === props.modelValue));

const visibleOptions = computed(() => {
  if (!props.filterable) return props.options;
  const k = filter.value.trim().toLowerCase();
  if (!k) return props.options;
  return props.options.filter((o) => o.label.toLowerCase().includes(k));
});

watch(open, async (v) => {
  if (v && props.filterable) {
    filter.value = "";
    await nextTick();
    searchInput.value?.focus();
  }
});

function pick(o: Opt) {
  tracer.api("GlassSelect:pick", `选中选项: ${o.label} (${o.value})`, {});
  emit("update:modelValue", o.value);
  open.value = false;
}
</script>

<template>
  <div class="gselect">
    <button
      type="button"
      class="gselect__trigger"
      :class="{ 'is-open': open }"
      :disabled="disabled"
      @click="open = !open"
    >
      <span :class="current ? 'gselect__value' : 'gselect__ph'">
        {{ current?.label || placeholder }}
      </span>
      <svg
        class="gselect__chevron"
        :class="{ 'is-open': open }"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
    </button>

    <transition name="gselect-pop">
      <div v-if="open" class="gselect__panel">
        <div v-if="filterable" class="gselect__search">
          <input
            ref="searchInput"
            v-model="filter"
            type="text"
            class="gselect__search-input"
            placeholder="输入以筛选..."
            @click.stop
          />
        </div>
        <div class="gselect__list">
          <button
            v-for="o in visibleOptions"
            :key="o.value"
            type="button"
            class="gselect__option"
            :class="{ 'is-active': o.value === modelValue }"
            @click="pick(o)"
          >
            <span>{{ o.label }}</span>
            <svg
              v-if="o.value === modelValue"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <path d="M5 12l5 5L20 7" />
            </svg>
          </button>
          <div v-if="!visibleOptions.length" class="gselect__empty">无匹配项</div>
        </div>
      </div>
    </transition>

    <div v-if="open" class="gselect__backdrop" @click="open = false" />
  </div>
</template>

<style scoped>
.gselect {
  position: relative;
}
.gselect__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  width: 100%;
  padding: 0.55rem 0.85rem;
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--fg);
  font-size: 0.875rem;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.gselect__trigger:hover,
.gselect__trigger.is-open {
  border-color: var(--glass-border-hover);
}
.gselect__trigger.is-open {
  box-shadow: 0 0 0 3px var(--glass-bg-active);
}
.gselect__trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.gselect__value,
.gselect__ph {
  flex: 1;
  min-width: 0;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow: hidden;
}
.gselect__ph {
  color: var(--fg-subtle);
}
.gselect__chevron {
  color: var(--fg-subtle);
  flex-shrink: 0;
  transition: transform var(--dur) var(--ease);
}
.gselect__chevron.is-open {
  transform: rotate(180deg);
}
.gselect__panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 50;
  padding: 0.3rem;
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
}
.gselect__backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
}
.gselect__search {
  padding: 0.15rem 0.15rem 0.35rem;
}
.gselect__search-input {
  width: 100%;
  padding: 0.45rem 0.6rem;
  border-radius: 10px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--fg);
  font-size: 0.82rem;
  outline: none;
}
.gselect__search-input:focus {
  border-color: var(--glass-border-hover);
}
.gselect__list {
  max-height: 240px;
  overflow-y: auto;
}
.gselect__empty {
  padding: 0.6rem;
  text-align: center;
  color: var(--fg-subtle);
  font-size: 0.8rem;
}
.gselect__option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 0.85rem;
  cursor: pointer;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.gselect__option:hover {
  background: var(--glass-bg-hover);
  color: var(--fg);
}
.gselect__option.is-active {
  background: var(--glass-bg-active);
  color: var(--fg);
  font-weight: 500;
}
.gselect-pop-enter-active,
.gselect-pop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.gselect-pop-enter-from,
.gselect-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
