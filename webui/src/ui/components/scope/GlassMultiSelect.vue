<!-- GlassMultiSelect.vue — 自定义毛玻璃多选下拉选择 -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { tracer } from "@/utils/tracer";

const props = withDefaults(
  defineProps<{
    modelValue: string[]; // 已选中的字符串数组
    options: string[];    // 待选的字符串列表
    label: string;        // 下拉框前缀标签（如：城市、经验）
    placeholder?: string;
    filterable?: boolean; // 是否开启过滤搜索
  }>(),
  { placeholder: "请选择", filterable: true }
);

const emit = defineEmits<{
  (e: "update:modelValue", v: string[]): void;
}>();

const open = ref(false);
const filter = ref("");
const searchInput = ref<HTMLInputElement | null>(null);

// 搜索过滤后的选项
const visibleOptions = computed(() => {
  if (!props.filterable) return props.options;
  const k = filter.value.trim().toLowerCase();
  if (!k) return props.options;
  return props.options.filter((o) => o.toLowerCase().includes(k));
});

// 打开面板时自动聚焦搜索框
watch(open, async (v) => {
  if (v && props.filterable) {
    filter.value = "";
    await nextTick();
    searchInput.value?.focus();
  }
});

// 切换某个选项的选中状态
function toggle(o: string) {
  const list = props.modelValue;
  const newList = list.includes(o)
    ? list.filter((x) => x !== o)
    : [...list, o];
  tracer.api("GlassMultiSelect:toggle", `切换多选: ${o}`, { newValue: newList });
  emit("update:modelValue", newList);
}

// 清除所有选中项
function clearAll() {
  tracer.api("GlassMultiSelect:clear", `清除全部已选: ${props.label}`, {});
  emit("update:modelValue", []);
}

// 触发器显示的文本
const triggerText = computed(() => {
  if (props.modelValue.length === 0) return `${props.label}: 全部`;
  if (props.modelValue.length === 1) return `${props.label}: ${props.modelValue[0]}`;
  return `${props.label}: 已选 ${props.modelValue.length} 项`;
});
</script>

<template>
  <div class="gmulti-select">
    <!-- 下拉触发按钮 -->
    <button
      type="button"
      class="gmulti-select__trigger"
      :class="{ 'is-open': open, 'has-value': modelValue.length > 0 }"
      @click="open = !open"
    >
      <span class="gmulti-select__value">
        {{ triggerText }}
      </span>
      <svg
        class="gmulti-select__chevron"
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

    <!-- 下拉面板 -->
    <transition name="gselect-pop">
      <div v-if="open" class="gmulti-select__panel" @click.stop>
        <!-- 搜索过滤输入框 -->
        <div v-if="filterable" class="gmulti-select__search">
          <input
            ref="searchInput"
            v-model="filter"
            type="text"
            class="gmulti-select__search-input"
            placeholder="输入以搜索..."
          />
        </div>
        <!-- 选项列表 -->
        <div class="gmulti-select__list">
          <button
            v-for="o in visibleOptions"
            :key="o"
            type="button"
            class="gmulti-select__option"
            :class="{ 'is-active': modelValue.includes(o) }"
            @click="toggle(o)"
          >
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="modelValue.includes(o)"
                class="gmulti-select__checkbox"
                @click.prevent
              />
              <span>{{ o }}</span>
            </div>
          </button>
          <div v-if="!visibleOptions.length" class="gmulti-select__empty">无匹配项</div>
        </div>
        <!-- 底部清除区域 -->
        <div v-if="modelValue.length" class="gmulti-select__footer">
          <button type="button" class="gmulti-select__clear-btn" @click="clearAll">
            清除全部
          </button>
        </div>
      </div>
    </transition>

    <!-- 点击空白处关闭 -->
    <div v-if="open" class="gmulti-select__backdrop" @click="open = false" />
  </div>
</template>

<style scoped>
.gmulti-select {
  position: relative;
  display: inline-block;
}
.gmulti-select__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius-pill, 999px);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--fg-muted);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s ease;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.gmulti-select__trigger:hover,
.gmulti-select__trigger.is-open {
  border-color: var(--glass-border-hover);
  color: var(--fg);
}
/* 选中状态变成亮色强调 */
.gmulti-select__trigger.has-value {
  background: var(--accent-bg, rgba(0, 168, 150, 0.1));
  border-color: var(--accent);
  color: var(--accent);
}
.gmulti-select__chevron {
  color: var(--fg-subtle);
  transition: transform 0.15s ease;
}
.gmulti-select__chevron.is-open {
  transform: rotate(180deg);
}
.gmulti-select__panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 160px;
  max-width: 240px;
  z-index: 50;
  padding: 0.3rem;
  border-radius: var(--radius-md, 12px);
  background: var(--bg-panel);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
}
.gmulti-select__backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
}
.gmulti-select__search {
  padding: 0.15rem 0.15rem 0.35rem;
}
.gmulti-select__search-input {
  width: 100%;
  padding: 0.35rem 0.5rem;
  border-radius: 8px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--fg);
  font-size: 11px;
  outline: none;
}
.gmulti-select__search-input:focus {
  border-color: var(--glass-border-hover);
}
.gmulti-select__list {
  max-height: 200px;
  overflow-y: auto;
}
.gmulti-select__empty {
  padding: 0.5rem;
  text-align: center;
  color: var(--fg-subtle);
  font-size: 11px;
}
.gmulti-select__option {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 0.4rem 0.5rem;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 11px;
  cursor: pointer;
  text-align: left;
  transition: all 0.12s ease;
}
.gmulti-select__option:hover {
  background: var(--glass-bg-hover);
  color: var(--fg);
}
.gmulti-select__option.is-active {
  color: var(--accent);
}
.gmulti-select__checkbox {
  pointer-events: none;
  width: 12px;
  height: 12px;
  accent-color: var(--accent);
}
.gmulti-select__footer {
  border-top: 1px solid var(--glass-border);
  padding: 0.3rem 0.15rem 0.15rem;
  margin-top: 0.2rem;
  text-align: right;
}
.gmulti-select__clear-btn {
  font-size: 10px;
  color: var(--fg-subtle);
  background: transparent;
  border: none;
  cursor: pointer;
}
.gmulti-select__clear-btn:hover {
  color: var(--danger, #ff5a5f);
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
