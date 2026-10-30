<script setup lang="ts">
import { computed, onMounted, ref, watch, type Ref } from "vue";
import { useEngine } from "@/stores/engine";
import { GlassSelect, GlassTag } from "@/ui";
import type { Job } from "@/api";
import { tracer } from "@/utils/tracer";

// ============================================================================
// 列定义（声明式）：key 是 Job 字段；render 返回 cell 显示文本/JSX
// ============================================================================
type CellRender = (j: Job) => string | string[];
interface ColumnDef {
  key: keyof Job | "skills" | "welfare" | "tags"; // 复合列也算
  title: string;
  defaultWidth: number;      // 初始宽度（px）
  minWidth?: number;
  align?: "left" | "center" | "right";
  defaultVisible?: boolean;  // 默认是否显示（高密度列默认隐藏）
  render?: CellRender;       // 自定义渲染
  // 排序键（可空：不可排序列置空）
  sortKey?: (j: Job) => string | number | null;
}

const COLUMNS: ColumnDef[] = [
  { key: "title",       title: "职位",    defaultWidth: 240, minWidth: 120, defaultVisible: true,
    sortKey: (j) => j.title ?? "" },
  { key: "company",     title: "公司",    defaultWidth: 180, minWidth: 100, defaultVisible: true,
    sortKey: (j) => j.company ?? "" },
  { key: "salary",      title: "薪资",    defaultWidth: 120, minWidth: 80,  defaultVisible: true,
    sortKey: (j) => parseSalary(j.salary)?.[0] ?? null },
  { key: "location",    title: "城市",    defaultWidth: 100, minWidth: 70,  defaultVisible: true,
    sortKey: (j) => j.location ?? "" },
  { key: "experience",  title: "经验",    defaultWidth: 80,  minWidth: 60,  defaultVisible: true,
    sortKey: (j) => j.experience ?? "" },
  { key: "degree",      title: "学历",    defaultWidth: 80,  minWidth: 60,  defaultVisible: true,
    sortKey: (j) => j.degree ?? "" },
  { key: "industry",    title: "行业",    defaultWidth: 120, minWidth: 80,  defaultVisible: false,
    sortKey: (j) => j.industry ?? "" },
  { key: "boss_name",   title: "招聘者",  defaultWidth: 120, minWidth: 80,  defaultVisible: true,
    sortKey: (j) => j.boss_name ?? "" },
  { key: "skills",      title: "技能",    defaultWidth: 200, minWidth: 120, defaultVisible: false,
    render: (j) => j.skills ?? [] },
  { key: "welfare",     title: "福利",    defaultWidth: 200, minWidth: 120, defaultVisible: false,
    render: (j) => j.welfare ?? [] },
  { key: "tags",        title: "标签",    defaultWidth: 160, minWidth: 100, defaultVisible: false,
    render: (j) => j.job_labels ?? [] },
];

// ============================================================================
// 解析薪资字符串为 [min,max]（单位 K）。无法解析（如「面议」）返回 null。
// ============================================================================
function parseSalary(text?: string): [number, number] | null {
  if (!text) return null;
  const s = String(text);
  if (/\/(天|时|小时)|元\/(天|时|小时)/.test(s)) return null;
  let m = s.match(/(\d+(?:\.\d+)?)\s*[-~―]\s*(\d+(?:\.\d+)?)\s*[Kk]/);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  m = s.match(/(\d+(?:\.\d+)?)\s*万?\s*[-~―]\s*(\d+(?:\.\d+)?)\s*万/);
  if (m) return [parseFloat(m[1]) * 10, parseFloat(m[2]) * 10];
  m = s.match(/(\d+(?:\.\d+)?)\s*千?\s*[-~―]\s*(\d+(?:\.\d+)?)\s*千/);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  m = s.match(/(\d+(?:\.\d+)?)\s*[Kk]/);
  if (m) return [parseFloat(m[1]), parseFloat(m[1])];
  return null;
}

// ============================================================================
// store
// ============================================================================
const engine = useEngine();

// ============================================================================
// 顶部筛选栏
// ============================================================================
const keyword = ref("");
const salaryMin = ref<number | null>(null);
const salaryMax = ref<number | null>(null);
const skillFilter = ref<string[]>([]); // 选中技能：只要命中其中一个就通过（OR）
const welfareFilter = ref<string[]>([]);
const tagFilter = ref<string[]>([]);
const selected = ref<Job | null>(null);

onMounted(() => {
  if (!engine.jobs.length) engine.loadResults();
});

// 显示层薪资过滤：纯展示，无法解析的薪资不会被滤掉
function salaryPass(text?: string): boolean {
  const lo = salaryMin.value;
  const hi = salaryMax.value;
  if (lo == null && hi == null) return true;
  const r = parseSalary(text);
  if (!r) return true;
  if (lo != null && r[1] < lo) return false;
  if (hi != null && r[0] > hi) return false;
  return true;
}

// 集合类筛选（任一命中即通过）：空数组 = 不过滤
function setPass<T>(needles: T[], haystack: T[] | undefined): boolean {
  if (!needles.length) return true;
  if (!haystack?.length) return false;
  return needles.some((n) => haystack.includes(n));
}

// ============================================================================
// 全量数据上的派生：可选值字典（用于筛选面板的多选 chips）
// ============================================================================
const skillOptions = computed(() =>
  Array.from(
    new Set(engine.jobs.flatMap((j) => j.skills ?? []))
  ).sort().slice(0, 80) // 上限避免海量 chip
);
const welfareOptions = computed(() =>
  Array.from(
    new Set(engine.jobs.flatMap((j) => j.welfare ?? []))
  ).sort().slice(0, 80)
);
const tagOptions = computed(() =>
  Array.from(
    new Set(engine.jobs.flatMap((j) => j.job_labels ?? []))
  ).sort().slice(0, 80)
);

// ============================================================================
// 过滤主链
// ============================================================================
const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase();
  return engine.jobs.filter((j) => {
    if (!salaryPass(j.salary)) return false;
    if (!setPass(skillFilter.value, j.skills)) return false;
    if (!setPass(welfareFilter.value, j.welfare)) return false;
    if (!setPass(tagFilter.value, j.job_labels)) return false;
    if (!k) return true;
    return [
      j.title, j.company, j.location, j.salary, j.industry,
      j.boss_name, j.experience, j.degree,
      ...(j.skills ?? []), ...(j.welfare ?? []), ...(j.job_labels ?? []),
    ].join(" ").toLowerCase().includes(k);
  });
});

// ============================================================================
// 列显隐 + 列宽（响应式），localStorage 持久化
// ============================================================================
const STORAGE_KEY = "resultTable:v1";
interface Persisted {
  visible: Record<string, boolean>;
  widths: Record<string, number>;
}

function loadPersisted(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { visible: {}, widths: {} };
    const p = JSON.parse(raw);
    return {
      visible: p?.visible ?? {},
      widths: p?.widths ?? {},
    };
  } catch {
    return { visible: {}, widths: {} };
  }
}
const persisted = loadPersisted();

const visibleCols = ref<Record<string, boolean>>(
  Object.fromEntries(
    COLUMNS.map((c) => [c.key, persisted.visible[c.key] ?? c.defaultVisible ?? true])
  )
);
const colWidths = ref<Record<string, number>>(
  Object.fromEntries(COLUMNS.map((c) => [c.key, persisted.widths[c.key] ?? c.defaultWidth]))
);

// 任何显隐 / 宽度变动都持久化（防抖由 watch 的 flush:'post' + 同步 write 简化处理）
watch(
  [visibleCols, colWidths],
  () => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ visible: visibleCols.value, widths: colWidths.value })
      );
    } catch { /* 忽略容量错误 */ }
  },
  { deep: true }
);

const visibleColumnList = computed(() =>
  COLUMNS.filter((c) => visibleCols.value[c.key])
);

// 列设置面板
const showColPanel = ref(false);

// ============================================================================
// 列宽拖拽（指令式，自写：避免引入 vxe-table 这种重型库）
// 拖拽期间通过 CSS 变量覆盖 width，不触发 Vue 重排
// ============================================================================
function onResizeStart(e: MouseEvent, colKey: string) {
  e.preventDefault();
  e.stopPropagation();
  const startX = e.clientX;
  const startW = colWidths.value[colKey] ?? 100;
  const minW = COLUMNS.find((c) => c.key === colKey)?.minWidth ?? 60;

  const ths = document.querySelectorAll<HTMLTableCellElement>(
    `th[data-col="${colKey}"], td[data-col="${colKey}"]`
  );
  ths.forEach((el) => (el.style.width = startW + "px"));

  const onMove = (ev: MouseEvent) => {
    const w = Math.max(minW, startW + (ev.clientX - startX));
    ths.forEach((el) => (el.style.width = w + "px"));
  };
  const onUp = (ev: MouseEvent) => {
    const w = Math.max(minW, startW + (ev.clientX - startX));
    colWidths.value[colKey] = Math.round(w);
    ths.forEach((el) => (el.style.width = ""));
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  };
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

// ============================================================================
// 排序（点列头切换 asc/desc/none）
// ============================================================================
type SortDir = "asc" | "desc" | null;
const sortKey = ref<string | null>(null);
const sortDir = ref<SortDir>(null);

function clickHeader(col: ColumnDef) {
  if (!col.sortKey) return;
  if (sortKey.value !== col.key) {
    sortKey.value = col.key as string;
    sortDir.value = "asc";
  } else if (sortDir.value === "asc") {
    sortDir.value = "desc";
  } else {
    sortKey.value = null;
    sortDir.value = null;
  }
}

const sortedFiltered = computed(() => {
  if (!sortKey.value || !sortDir.value) return filtered.value;
  const col = COLUMNS.find((c) => c.key === sortKey.value);
  if (!col?.sortKey) return filtered.value;
  const key = col.sortKey;
  const dir = sortDir.value === "asc" ? 1 : -1;
  // 复制后排序，避免污染原数组（filter 已生成新数组，但保险起见）
  return [...filtered.value].sort((a, b) => {
    const va = key(a);
    const vb = key(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;   // null 排最后
    if (vb == null) return -1;
    if (va < vb) return -1 * dir;
    if (va > vb) return  1 * dir;
    return 0;
  });
});

// ============================================================================
// CSV 导出（按当前可见列导出，列宽与列顺序与表头一致）
// ============================================================================
function exportCsv() {
  const cols = visibleColumnList.value;
  const header = cols.map((c) => `"${c.title}"`).join(",");
  const rows = sortedFiltered.value.map((j) =>
    cols.map((c) => {
      const v = c.render ? c.render(j) : (j as any)[c.key];
      const text = Array.isArray(v) ? v.join(" / ") : (v ?? "");
      return `"${String(text).replace(/"/g, '""')}"`;
    }).join(",")
  );
  const csv = "\uFEFF" + [header, ...rows].join("\n");
  const filename = (engine.currentFile || "jobs").replace(/\.json$/, "") + ".csv";

  // 增加极其详细的 debugtracer 追踪
  tracer.log({ layer: "FE-ACTION", fn: "ResultTable:exportCsv", msg: `导出 CSV: ${filename}`, scope: "export-csv", data: {
    filename,
    rowsCount: rows.length,
    columns: cols.map((c) => c.title),
    sourceFile: engine.currentFile || "default",
    filters: {
      keyword: keyword.value,
      salaryMin: salaryMin.value,
      salaryMax: salaryMax.value,
      skills: skillFilter.value,
      welfare: welfareFilter.value,
      tags: tagFilter.value,
    }
  }});

  const pywebview = (window as any).pywebview;
  if (pywebview?.api?.save_file) {
    pywebview.api.save_file(filename, csv).then((savePath: string) => {
      if (savePath) {
        tracer.log({ layer: "FE-ACTION", fn: "ResultTable:exportCsv", msg: `文件已通过 App 成功保存`, data: { filename, savePath }, scope: "export-csv" });
      } else {
        tracer.log({ layer: "FE-ACTION", fn: "ResultTable:exportCsv", msg: `用户取消了文件保存或保存失败`, data: { filename }, scope: "export-csv" });
      }
    });
  } else {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
    tracer.log({ layer: "FE-ACTION", fn: "ResultTable:exportCsv", msg: `文件已通过浏览器触发下载: ${filename}`, data: { filename }, scope: "export-csv" });
  }
}

// ============================================================================
// 工具：清空筛选
// ============================================================================
const hasActiveFilter = computed(() =>
  !!keyword.value.trim() ||
  salaryMin.value != null || salaryMax.value != null ||
  skillFilter.value.length || welfareFilter.value.length || tagFilter.value.length
);

function clearFilters() {
  keyword.value = "";
  salaryMin.value = null;
  salaryMax.value = null;
  skillFilter.value = [];
  welfareFilter.value = [];
  tagFilter.value = [];
}

// ============================================================================
// 文件切换
// ============================================================================
const fileOptions = computed(() =>
  engine.resultFiles.map((f) => ({ label: f, value: f }))
);
function onFileChange(v: string) {
  engine.loadResults(v.replace("jobs_", "").replace(".json", ""));
}

// ============================================================================
// 渲染辅助：把列的 render 输出（字符串 | 字符串数组）渲染成 GlassTag 或文本
// ============================================================================
function isTagList(v: unknown): v is string[] {
  return Array.isArray(v);
}

// 切换筛选 chip 选中状态
function toggleChip(arr: string[], v: string) {
  const i = arr.indexOf(v);
  if (i >= 0) arr.splice(i, 1);
  else arr.push(v);
}
</script>

<template>
  <div class="card flex flex-col overflow-x-hidden">
    <!-- ============================== 顶部工具栏 ============================== -->
    <div class="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-bg-border">
      <span class="text-sm font-semibold text-fg">岗位列表</span>
      <span class="text-[11px] text-fg-subtle">
        {{ filtered.length }} / {{ engine.jobs.length }} 条
      </span>

      <div v-if="engine.resultFiles.length" class="w-52">
        <GlassSelect
          :model-value="engine.currentFile || ''"
          :options="fileOptions"
          @update:model-value="onFileChange"
        />
      </div>

      <div class="flex-1"></div>

      <!-- 薪资范围 -->
      <div class="flex items-center gap-1 text-xs text-fg-subtle">
        <span>薪资</span>
        <input
          v-model.number="salaryMin"
          type="number" min="0" placeholder="最低"
          class="input !w-16 !py-1.5 text-xs"
        />
        <span>~</span>
        <input
          v-model.number="salaryMax"
          type="number" min="0" placeholder="最高"
          class="input !w-16 !py-1.5 text-xs"
        />
        <span>K</span>
      </div>

      <input
        v-model="keyword" placeholder="搜索职位/公司/技能/福利..."
        class="input !w-56 !py-1.5 text-xs"
      />

      <button
        v-if="hasActiveFilter"
        class="btn-ghost !py-1.5 text-xs"
        @click="clearFilters"
      >清空筛选</button>

      <button
        class="btn-ghost !py-1.5 text-xs"
        :class="{ 'is-on': showColPanel }"
        @click="showColPanel = !showColPanel"
      >列设置</button>

      <button class="btn-ghost !py-1.5 text-xs" @click="engine.loadResults()">刷新</button>
      <button class="btn-primary !py-1.5 text-xs" @click="exportCsv">导出 CSV</button>
    </div>

    <!-- ============================== 集合筛选条（chips） ============================== -->
    <div
      v-if="skillOptions.length || welfareOptions.length || tagOptions.length"
      class="px-4 py-2 border-b border-bg-border flex flex-wrap gap-x-4 gap-y-1.5"
    >
      <!-- 技能 -->
      <div v-if="skillOptions.length" class="flex items-center gap-1.5 min-w-0">
        <span class="text-[11px] text-fg-subtle shrink-0">技能</span>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="s in skillOptions"
            :key="'sk-' + s"
            type="button"
            class="chip"
            :class="{ 'is-on': skillFilter.includes(s) }"
            :title="`仅显示包含「${s}」的岗位`"
            @click="toggleChip(skillFilter, s)"
          >{{ s }}</button>
        </div>
      </div>
      <!-- 福利 -->
      <div v-if="welfareOptions.length" class="flex items-center gap-1.5 min-w-0">
        <span class="text-[11px] text-fg-subtle shrink-0">福利</span>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="s in welfareOptions"
            :key="'wf-' + s"
            type="button"
            class="chip"
            :class="{ 'is-on': welfareFilter.includes(s) }"
            @click="toggleChip(welfareFilter, s)"
          >{{ s }}</button>
        </div>
      </div>
      <!-- 标签 -->
      <div v-if="tagOptions.length" class="flex items-center gap-1.5 min-w-0">
        <span class="text-[11px] text-fg-subtle shrink-0">标签</span>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="s in tagOptions"
            :key="'tg-' + s"
            type="button"
            class="chip"
            :class="{ 'is-on': tagFilter.includes(s) }"
            @click="toggleChip(tagFilter, s)"
          >{{ s }}</button>
        </div>
      </div>
    </div>

    <!-- ============================== 列设置面板（浮层） ============================== -->
    <transition name="slide-down">
      <div
        v-if="showColPanel"
        class="px-4 py-3 border-b border-bg-border bg-bg-raised/40 grid gap-1.5"
        style="grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));"
      >
        <label
          v-for="c in COLUMNS"
          :key="'vis-' + c.key"
          class="flex items-center gap-2 text-xs text-fg-muted cursor-pointer select-none"
        >
          <input
            type="checkbox"
            :checked="visibleCols[c.key]"
            class="gcheck-native"
            @change="visibleCols[c.key] = ($event.target as HTMLInputElement).checked"
          />
          <span>{{ c.title }}</span>
          <span class="text-[10px] text-fg-subtle ml-auto">{{ colWidths[c.key] }}px</span>
        </label>
      </div>
    </transition>

    <!-- ============================== 表格（只横滚；竖滚交给 main） ============================== -->
    <div class="overflow-x-auto">
      <table class="w-full text-sm border-collapse" style="table-layout: fixed;">
        <colgroup>
          <col
            v-for="c in visibleColumnList"
            :key="'cg-' + c.key"
            :style="{ width: colWidths[c.key] + 'px' }"
          />
        </colgroup>
        <thead class="bg-bg-panel">
          <tr class="text-left text-xs text-fg-subtle border-b border-bg-border">
            <th
              v-for="c in visibleColumnList"
              :key="'th-' + c.key"
              :data-col="c.key"
              class="relative px-3 py-2.5 font-medium select-none"
              :class="[
                c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : 'text-left',
                c.sortKey ? 'cursor-pointer hover:text-fg' : ''
              ]"
              @click="clickHeader(c)"
            >
              <span class="inline-flex items-center gap-1">
                <span>{{ c.title }}</span>
                <span v-if="sortKey === c.key" class="text-fg">
                  {{ sortDir === 'asc' ? '↑' : '↓' }}
                </span>
              </span>
              <!-- 拖拽手柄 -->
              <span
                class="resize-handle"
                @mousedown="(e) => onResizeStart(e, c.key as string)"
                @click.stop
                :title="`拖动调整「${c.title}」宽度`"
              ></span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(j, i) in sortedFiltered"
            :key="(j.collected_at || '') + '-' + i"
            class="row-job border-b border-bg-border hover:bg-bg-raised cursor-pointer transition-colors"
            @click="selected = j"
          >
            <td
              v-for="c in visibleColumnList"
              :key="'td-' + c.key + '-' + i"
              :data-col="c.key"
              class="px-3 py-2.5"
              :class="c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : ''"
            >
              <!-- 文本列 -->
              <template v-if="!c.render">
                <span class="text-fg font-medium truncate-cell">{{ (j as any)[c.key] || '-' }}</span>
              </template>
              <!-- 复合列（数组 → tags） -->
              <template v-else-if="c.key === 'skills' || c.key === 'welfare' || c.key === 'tags'">
                <span
                  v-if="!(c.render(j) as string[]).length"
                  class="text-fg-subtle"
                >-</span>
                <span v-else class="flex flex-wrap gap-1">
                  <GlassTag
                    v-for="t in (c.render(j) as string[])"
                    :key="t"
                    :variant="
                      c.key === 'skills' ? 'brand' :
                      c.key === 'welfare' ? 'success' : 'default'
                    "
                  >{{ t }}</GlassTag>
                </span>
              </template>
              <!-- 数值列：薪资高亮 -->
              <template v-else-if="c.key === 'salary'">
                <span class="text-fg whitespace-nowrap font-medium">{{ j.salary || '-' }}</span>
              </template>
              <!-- 其他自定义 render 退化为字符串 -->
              <template v-else>
                <span class="text-fg-muted truncate-cell">{{ c.render(j) }}</span>
              </template>
            </td>
          </tr>
          <tr v-if="!sortedFiltered.length">
            <td
              :colspan="visibleColumnList.length"
              class="px-4 py-10 text-center text-fg-subtle"
            >
              {{ hasActiveFilter ? '当前筛选条件下没有匹配的岗位。' : '暂无数据。启动后这里会整理并显示岗位列表。' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ============================== 详情抽屉 ============================== -->
    <transition name="slide">
      <div
        v-if="selected"
        class="fixed inset-0 z-40 flex justify-end bg-black/50"
        @click.self="selected = null"
      >
        <div class="w-[520px] max-w-full h-full bg-bg-panel border-l border-bg-border p-6 overflow-y-auto animate-fade-in">
          <div class="flex items-start justify-between">
            <div>
              <h3 class="text-lg font-semibold text-fg">{{ selected.title }}</h3>
              <p class="text-fg mt-1 font-medium">{{ selected.salary }}</p>
            </div>
            <button class="btn-ghost !p-2" @click="selected = null">✕</button>
          </div>
          <div class="mt-4 space-y-2 text-sm text-fg-muted">
            <p>
              <span class="text-fg-subtle">公司：</span>
              {{ selected.company }} ({{ selected.company_stage }} · {{ selected.company_scale }})
            </p>
            <p>
              <span class="text-fg-subtle">城市：</span>
              {{ selected.location }} · {{ selected.address }}
            </p>
            <p>
              <span class="text-fg-subtle">要求：</span>
              {{ selected.experience }} / {{ selected.degree }}
            </p>
            <p><span class="text-fg-subtle">行业：</span>{{ selected.industry }}</p>
            <p>
              <span class="text-fg-subtle">招聘者：</span>
              {{ selected.boss_name }} - {{ selected.boss_title }} ({{ selected.boss_active }})
            </p>
            <p v-if="selected.skills?.length">
              <span class="text-fg-subtle">技能：</span>
              <GlassTag
                v-for="s in selected.skills" :key="s"
                variant="brand" class="mr-1 mb-1"
              >{{ s }}</GlassTag>
            </p>
            <p v-if="selected.welfare?.length">
              <span class="text-fg-subtle">福利：</span>
              <GlassTag
                v-for="s in selected.welfare" :key="s"
                variant="success" class="mr-1 mb-1"
              >{{ s }}</GlassTag>
            </p>
            <p v-if="selected.job_labels?.length">
              <span class="text-fg-subtle">标签：</span>
              <GlassTag
                v-for="s in selected.job_labels" :key="s"
                class="mr-1 mb-1"
              >{{ s }}</GlassTag>
            </p>
          </div>
          <div v-if="selected.jd" class="mt-5">
            <h4 class="text-sm font-semibold text-fg mb-2">职位描述</h4>
            <pre class="text-xs text-fg-muted whitespace-pre-wrap font-sans leading-relaxed bg-bg-raised rounded-xl p-3">{{ selected.jd }}</pre>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/* 抽屉滑入 */
.slide-enter-active,
.slide-leave-active {
  transition: opacity 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
}

/* 列设置面板下拉 */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: max-height 0.2s ease, opacity 0.2s ease;
  overflow: hidden;
}
.slide-down-enter-from,
.slide-down-leave-to {
  max-height: 0;
  opacity: 0;
}
.slide-down-enter-to,
.slide-down-leave-from {
  max-height: 200px;
  opacity: 1;
}

/* 列宽拖拽手柄：放在列头右侧 6px 宽的竖条 */
.resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  user-select: none;
  touch-action: none;
}
.resize-handle:hover {
  background: linear-gradient(to right, transparent, rgba(255, 255, 255, 0.18));
}

/* 文本截断 */
.truncate-cell {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

/* 行 hover 反馈平滑 */
.row-job {
  transition: background-color 0.12s ease;
}

/* chip：集合筛选条上的小标签按钮 */
.chip {
  font-size: 11px;
  padding: 0.15rem 0.55rem;
  border-radius: var(--radius-pill, 999px);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--fg-muted);
  cursor: pointer;
  transition: all 0.12s ease;
  white-space: nowrap;
}
.chip:hover {
  border-color: var(--glass-border-hover);
  color: var(--fg);
}
.chip.is-on {
  background: var(--accent);
  border-color: transparent;
  color: var(--accent-fg);
}

/* 列设置面板里的原生 checkbox：复用玻璃风样式 */
.gcheck-native {
  appearance: none;
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  flex-shrink: 0;
  position: relative;
  margin: 0;
}
.gcheck-native:checked {
  background: var(--accent);
  border-color: transparent;
}
.gcheck-native:checked::after {
  content: "";
  position: absolute;
  left: 3px; top: 0px;
  width: 4px; height: 8px;
  border-right: 2px solid var(--accent-fg);
  border-bottom: 2px solid var(--accent-fg);
  transform: rotate(45deg);
}

/* 列设置按钮高亮态 */
.btn-ghost.is-on {
  background: var(--accent);
  color: var(--accent-fg);
}
</style>