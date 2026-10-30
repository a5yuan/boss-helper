<script setup lang="ts">
/**
 * FilterBar：顶部筛选栏（搜索 + 薪资范围 + 7 个集合 chip 多选）
 * 所有状态由父组件传入 + 通过 update:* 事件回传（保持单向数据流）。
 */
import { computed, ref } from "vue";
import { useEngine } from "@/stores/engine";
import { GlassSelect, GlassMultiSelect } from "@/ui";
import { tracer } from "@/utils/tracer";


const props = defineProps<{
  keyword: string;
  salaryFilter: string[];
  cityFilter: string[];
  experienceFilter: string[];
  degreeFilter: string[];
  skillFilter: string[];
  welfareFilter: string[];
  tagFilter: string[];
  companyLabelFilter: string[];
  cityOptions: string[];
  experienceOptions: string[];
  degreeOptions: string[];
  skillOptions: string[];
  welfareOptions: string[];
  tagOptions: string[];
  companyLabelOptions: string[];
  filteredCount: number;
  totalCount: number;
  hasActiveFilter: boolean;
}>();

const emit = defineEmits<{
  (e: "update:keyword", v: string): void;
  (e: "update:salaryFilter", v: string[]): void;
  (e: "update:cityFilter", v: string[]): void;
  (e: "update:experienceFilter", v: string[]): void;
  (e: "update:degreeFilter", v: string[]): void;
  (e: "update:skillFilter", v: string[]): void;
  (e: "update:welfareFilter", v: string[]): void;
  (e: "update:tagFilter", v: string[]): void;
  (e: "update:companyLabelFilter", v: string[]): void;
  (e: "clear"): void;
}>();

const engine = useEngine();

const fileOptions = computed(() =>
  engine.resultFiles.map((f) => ({ label: f, value: f }))
);
function onFileChange(v: string) {
  engine.loadResults(v.replace("jobs_", "").replace(".json", ""));
}
function refresh() {
  engine.loadResults();
}

// BOSS 直聘薪资标准档位（多选列表）
const SALARY_OPTIONS = ["3K 以下", "3-5K", "5-10K", "10-20K", "20-50K", "50K 以上"];

// chips 行折叠状态（仅控制下方 chips 行的展开/收起，不影响上方工具栏）
const chipsExpanded = ref(false);
</script>

<template>
  <!-- ============================== 顶部工具栏 ============================== -->
  <div class="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-bg-border">
    <span class="text-sm font-semibold text-fg">岗位列表</span>
    <span class="text-[11px] text-fg-subtle">
      {{ props.filteredCount }} / {{ props.totalCount }} 条
    </span>

    <div v-if="engine.resultFiles.length" class="min-w-52 max-w-80 w-auto">
      <GlassSelect
        :model-value="engine.currentFile || ''"
        :options="fileOptions"
        @update:model-value="onFileChange"
      />
    </div>

    <div class="flex-1"></div>

    <!-- 薪资范围（多选） -->
    <div class="flex items-center gap-1 text-xs text-fg-subtle">
      <GlassMultiSelect
        :model-value="props.salaryFilter"
        label="薪资"
        :options="SALARY_OPTIONS"
        :filterable="false"
        @update:model-value="emit('update:salaryFilter', $event)"
      />
    </div>

    <input
      :value="props.keyword"
      @input="emit('update:keyword', ($event.target as HTMLInputElement).value)"
      placeholder="搜索职位/公司/技能/福利..."
      class="input !w-56 !py-1.5 text-xs"
    />

    <button
      class="btn-ghost !py-1.5 text-xs flex items-center gap-1.5"
      :class="{ 'bg-white/10 text-fg border-glass-border-hover': chipsExpanded, 'text-accent border-accent/30': props.hasActiveFilter }"
      @click="chipsExpanded = !chipsExpanded"
      :title="chipsExpanded ? '隐藏筛选' : '展开筛选'"
    >
      <span>筛选</span>
      <svg
        class="transition-transform duration-200 opacity-60"
        :class="{ 'rotate-180': chipsExpanded }"
        width="10"
        height="10"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="3"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
      <span v-if="props.hasActiveFilter" class="w-1.5 h-1.5 rounded-full bg-accent shrink-0"></span>
    </button>

    <button class="btn-ghost !py-1.5 text-xs" @click="refresh">刷新</button>
  </div>

  <transition name="chip-collapse">
    <div
      v-if="chipsExpanded"
      class="px-4 py-2 border-b border-bg-border flex flex-wrap gap-2 items-center"
    >
      <GlassMultiSelect label="城市" :model-value="props.cityFilter" :options="props.cityOptions"
        @update:model-value="emit('update:cityFilter', $event)" />
      <GlassMultiSelect label="经验" :model-value="props.experienceFilter" :options="props.experienceOptions"
        @update:model-value="emit('update:experienceFilter', $event)" />
      <GlassMultiSelect label="学历" :model-value="props.degreeFilter" :options="props.degreeOptions"
        @update:model-value="emit('update:degreeFilter', $event)" />
      <GlassMultiSelect label="技能" :model-value="props.skillFilter" :options="props.skillOptions"
        @update:model-value="emit('update:skillFilter', $event)" />
      <GlassMultiSelect label="福利" :model-value="props.welfareFilter" :options="props.welfareOptions"
        @update:model-value="emit('update:welfareFilter', $event)" />
      <GlassMultiSelect label="岗位标签" :model-value="props.tagFilter" :options="props.tagOptions"
        @update:model-value="emit('update:tagFilter', $event)" />
      <GlassMultiSelect label="公司标签" :model-value="props.companyLabelFilter" :options="props.companyLabelOptions"
        @update:model-value="emit('update:companyLabelFilter', $event)" />

      <!-- 清空筛选（置于下拉列表末尾，避免顶部布局跳动） -->
      <button
        v-if="props.hasActiveFilter"
        class="text-[11px] px-2.5 py-1 rounded-full border border-danger/30 text-danger hover:bg-danger/10 hover:border-danger/50 transition-all duration-200 ml-1 shrink-0"
        @click="emit('clear')"
      >
        清空筛选
      </button>
    </div>
  </transition>
</template>

<style scoped>
.chip-collapse-enter-active,
.chip-collapse-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease, max-height 0.2s ease;
  overflow: hidden;
}
.chip-collapse-enter-from,
.chip-collapse-leave-to {
  opacity: 0;
  transform: translateY(-2px);
  max-height: 0;
}
.chip-collapse-enter-to,
.chip-collapse-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 250px;
}
</style>