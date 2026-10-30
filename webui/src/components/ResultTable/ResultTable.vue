<script setup lang="ts">
/**
 * ResultTable：组合 FilterBar + JobTable + JobDetailDrawer
 * 所有筛选状态/派生集中在 useJobFilters()；本组件只负责装配与选中态。
 */
import { ref, watch } from "vue";
import { useJobFilters } from "@/composables/useJobFilters";
import { tracer } from "@/utils/tracer";
import FilterBar from "./FilterBar.vue";
import JobTable from "./JobTable.vue";
import JobDetailDrawer from "./JobDetailDrawer.vue";
import type { Job } from "@/api";

const f = useJobFilters();
const selected = ref<Job | null>(null);

// 追踪 filtered 传给 JobTable 的时机与结果数
watch(
  () => f.filtered.value,
  (newFiltered) => {
    tracer.api("ResultTable:filtered", `filtered 传给 JobTable: ${newFiltered.length} 条`, {
      count: newFiltered.length,
      salaryFilter: f.salaryFilter.value,
    });
  }
);

// 各 filter 事件处理（抽成函数，避免 inline 表达式 TS 类型报错）
function onKeyword(v: string) { f.keyword.value = v; }
function onSalaryFilter(v: string[]) {
  tracer.api("ResultTable:salary-filter", `收到 salary-filter 事件: ${v}`, {});
  f.salaryFilter.value = v;
}
function onCityFilter(v: string[]) { f.cityFilter.value = v; }
function onExperienceFilter(v: string[]) { f.experienceFilter.value = v; }
function onDegreeFilter(v: string[]) { f.degreeFilter.value = v; }
function onSkillFilter(v: string[]) { f.skillFilter.value = v; }
function onWelfareFilter(v: string[]) { f.welfareFilter.value = v; }
function onTagFilter(v: string[]) { f.tagFilter.value = v; }
function onCompanyLabelFilter(v: string[]) { f.companyLabelFilter.value = v; }
</script>

<template>
  <div id="result-table-panel" class="result-table-root flex flex-col h-full overflow-hidden">
    <FilterBar
      :keyword="f.keyword.value"
      @update:keyword="onKeyword"
      :salary-filter="f.salaryFilter.value"
      @update:salary-filter="onSalaryFilter"
      :city-filter="f.cityFilter.value"
      @update:city-filter="onCityFilter"
      :experience-filter="f.experienceFilter.value"
      @update:experience-filter="onExperienceFilter"
      :degree-filter="f.degreeFilter.value"
      @update:degree-filter="onDegreeFilter"
      :skill-filter="f.skillFilter.value"
      @update:skill-filter="onSkillFilter"
      :welfare-filter="f.welfareFilter.value"
      @update:welfare-filter="onWelfareFilter"
      :tag-filter="f.tagFilter.value"
      @update:tag-filter="onTagFilter"
      :company-label-filter="f.companyLabelFilter.value"
      @update:company-label-filter="onCompanyLabelFilter"
      :city-options="f.cityOptions.value"
      :experience-options="f.experienceOptions.value"
      :degree-options="f.degreeOptions.value"
      :skill-options="f.skillOptions.value"
      :welfare-options="f.welfareOptions.value"
      :tag-options="f.tagOptions.value"
      :company-label-options="f.companyLabelOptions.value"
      :filtered-count="f.filteredCount.value"
      :total-count="f.totalCount.value"
      :has-active-filter="f.hasActiveFilter.value"
      @clear="f.clearFilters"
    />
    <JobTable :jobs="f.filtered.value" @select="(j) => (selected = j)" />
    <JobDetailDrawer :job="selected" @close="selected = null" />
  </div>
</template>