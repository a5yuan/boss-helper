<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useEngine } from "@/stores/engine";
import { GlassSelect, GlassCheckbox, GlassToggle, GlassMultiSelect, GlassDialog, GlassButton } from "@/ui";

defineEmits<{
  (e: "collapse"): void;
}>();

const engine = useEngine();

const browserOptions = [
  { label: "Chrome", value: "chrome" },
  { label: "Edge", value: "edge" },
];

onMounted(() => {
  if (!engine.cities.length) engine.loadCities();
});

function onBrowserChange(v: string) {
  engine.params.browser_type = v;
  engine.loadConfig();
}

function onCityChange(code: string) {
  engine.params.city_code = code || null;
  const hit = engine.cities.find((c) => c.value === code);
  engine.params.city_name = hit ? hit.label : null;
}

// 是否运行在桌面壳（pywebview 注入 API）；纯浏览器 dev 下回退为手动输入
const hasNativePicker = computed(
  () => typeof (window as any).pywebview?.api?.pick_folder === "function"
);

async function pickFolder() {
  const api = (window as any).pywebview?.api;
  if (!api?.pick_folder) return;
  const p = await api.pick_folder();
  if (p) engine.saveConfig({ output_dir: p });
}

async function pickBrowser() {
  const api = (window as any).pywebview?.api;
  if (!api?.pick_file) return;
  const p = await api.pick_file();
  if (p) engine.saveConfig({ browser_path: p });
}

async function resetBrowserPath() {
  await engine.saveConfig({ browser_path: "" });
}

function onBrowserPathChange(e: Event) {
  engine.saveConfig({ browser_path: (e.target as HTMLInputElement).value });
}
function onOutputDirChange(e: Event) {
  engine.saveConfig({ output_dir: (e.target as HTMLInputElement).value });
}

const tagDisplay = computed(() => {
  if (!engine.params.tag_sync) return engine.params.tag || "";
  const parts: string[] = [engine.params.query || "(搜索关键词)"];
  if (engine.params.salary_min || engine.params.salary_max) {
    const min = engine.params.salary_min ?? "";
    const max = engine.params.salary_max ?? "";
    parts.push(min && max ? `${min}-${max}K` : min ? `${min}K以上` : `${max}K以下`);
  }
  if (engine.params.city_name) parts.push(engine.params.city_name);
  parts.push(`共${engine.params.count}条`);
  return parts.join("_");
});

// BOSS 直聘薪资标准档位（按截图范围）
const SALARY_RANGE_OPTIONS = [
  { label: "不限",     value: "0-0"   },
  { label: "3K 以下", value: "0-3"   },
  { label: "3-5K",    value: "3-5"   },
  { label: "5-10K",   value: "5-10"  },
  { label: "10-20K",  value: "10-20" },
  { label: "20-50K",  value: "20-50" },
  { label: "50K 以上",value: "50-0"  },
];

const JOB_TYPE_OPTIONS = [
  { label: "不限", value: "" },
  { label: "全职", value: "1901" },
  { label: "兼职", value: "1903" },
  { label: "实习", value: "1902" },
];

const DEGREE_OPTIONS = ["初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"];
const DEGREE_MAPPING: Record<string, string> = {
  "初中及以下": "209",
  "中专/中技": "208",
  "高中": "206",
  "大专": "202",
  "本科": "203",
  "硕士": "204",
  "博士": "205"
};

const selectedDegrees = computed({
  get() {
    const codes = engine.params.degrees || [];
    const labels: string[] = [];
    for (const [label, code] of Object.entries(DEGREE_MAPPING)) {
      if (codes.includes(code)) {
        labels.push(label);
      }
    }
    return labels;
  },
  set(labels: string[]) {
    const codes = labels.map(l => DEGREE_MAPPING[l]).filter(Boolean);
    engine.params.degrees = codes;
  }
});

const EXPERIENCE_OPTIONS = ["在校生", "应届生", "经验不限", "1年以内", "1-3年", "3-5年", "5-10年", "10年以上"];
const EXPERIENCE_MAPPING: Record<string, string> = {
  "在校生": "108",
  "应届生": "102",
  "经验不限": "101",
  "1年以内": "103",
  "1-3年": "104",
  "3-5年": "105",
  "5-10年": "106",
  "10年以上": "107"
};

const selectedExperience = computed({
  get() {
    const codes = engine.params.experience || [];
    const labels: string[] = [];
    for (const [label, code] of Object.entries(EXPERIENCE_MAPPING)) {
      if (codes.includes(code)) {
        labels.push(label);
      }
    }
    return labels;
  },
  set(labels: string[]) {
    const codes = labels.map(l => EXPERIENCE_MAPPING[l]).filter(Boolean);
    engine.params.experience = codes;
  }
});

// 从 engine.params 同步到下拉框当前值
const salaryRangeValue = ref("0-0");
function syncSalaryFromParams() {
  const min = engine.params.salary_min ?? 0;
  const max = engine.params.salary_max ?? 0;
  salaryRangeValue.value = `${min}-${max}`;
}
syncSalaryFromParams();

// 监听 engine.params 的变化，同步回 salaryRangeValue（避免用户改了代码里的默认值但 UI 不同步）
watch(
  () => [engine.params.salary_min, engine.params.salary_max],
  () => syncSalaryFromParams()
);

// 用户改了选项时，把 min/max 写回 engine.params
watch(salaryRangeValue, (v) => {
  const [minStr, maxStr] = v.split("-");
  const min = parseInt(minStr) || 0;
  const max = parseInt(maxStr) || 0;
  engine.params.salary_min = min === 0 ? null : min;
  engine.params.salary_max = max === 0 ? null : max;
  if (v === "0-0") {
    engine.params.salary_fuzzy = false;
  }
});

const showResetConfirm = ref(false);

function resetConfig() {
  showResetConfirm.value = true;
}

async function confirmReset() {
  showResetConfirm.value = false;
  await engine.resetParams();
}
</script>

<template>
  <aside id="config-panel" class="card p-5 w-full h-full flex flex-col gap-5 overflow-hidden lg:overflow-y-auto">
    <div class="flex items-start justify-between gap-2">
      <div>
        <div class="flex items-center gap-2 mb-0.5">
          <h2 class="text-sm font-semibold text-fg">运行配置</h2>
          <button
            type="button"
            class="text-[11px] text-fg-subtle hover:text-fg transition-colors font-normal cursor-pointer select-none"
            title="恢复默认配置"
            :disabled="engine.running"
            @click="resetConfig"
          >
            恢复默认
          </button>
        </div>
        <p class="text-xs text-fg-subtle">设置后点击右侧「启动助手」</p>
      </div>
      <!-- 折叠手柄：箭头指向左侧（折叠后方向是反向） -->
      <button
        type="button"
        class="shrink-0 w-7 h-7 -mt-1 -mr-1 rounded-lg border border-bg-border bg-bg-raised/60 text-fg-muted hover:text-fg hover:bg-bg-raised transition-colors flex items-center justify-center"
        aria-label="折叠配置面板"
        title="折叠配置面板"
        @click="$emit('collapse')"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
    </div>

    <!-- 关键词搜索路线开关 -->
    <div id="keyword-search-card" class="rounded-xl bg-bg-raised/60 border border-bg-border p-3">
      <label class="flex items-center justify-between cursor-pointer">
        <span class="text-sm font-medium text-fg">关键词搜索</span>
        <GlassToggle v-model="engine.params.keyword_search" :disabled="engine.running" />
      </label>
      <p class="text-[11px] text-fg-subtle mt-1.5 leading-relaxed">
        {{
          engine.params.keyword_search
            ? "开启：输入关键词后自动跳转到搜索页辅助分析"
            : "关闭：手动模式，请在浏览器中自行搜索后再运行助手"
        }}
      </p>
    </div>

    <!-- 搜索关键词（关键词路线，必填） -->
    <div v-if="engine.params.keyword_search">
      <label class="field-label">
        搜索岗位 <span class="text-danger">*</span>
      </label>
      <input
        v-model="engine.params.query"
        type="text"
        placeholder="例如 AI、运营、前端"
        class="input"
        :class="{ 'input-error': !engine.params.query.trim() }"
        :disabled="engine.running"
      />
      <p class="text-[11px] text-fg-subtle mt-1">必填，提交后自动跳转到对应搜索结果页</p>
    </div>

    <!-- 城市（仅关键词路线） -->
    <div v-if="engine.params.keyword_search">
      <label class="field-label flex items-center justify-between">
        <span>城市</span>
        <button
          type="button"
          class="text-[11px] text-fg-subtle hover:text-fg transition-colors disabled:opacity-50"
          :disabled="engine.running || engine.citiesRefreshing"
          title="基于已登录的浏览器获取城市列表"
          @click="engine.refreshCities()"
        >
          {{ engine.citiesRefreshing ? "刷新中..." : "↻ 刷新" }}
        </button>
      </label>
      <GlassSelect
        :model-value="engine.params.city_code || ''"
        :options="engine.cities"
        :disabled="engine.running"
        filterable
        placeholder="默认浏览器当前城市"
        @update:model-value="onCityChange"
      />
    </div>

    <!-- 获取数量 -->
    <div>
      <label class="field-label">获取数量</label>
      <input
        v-model.number="engine.params.count"
        type="number"
        min="1"
        max="500"
        class="input"
        :disabled="engine.running"
      />
    </div>

    <!-- 薪资范围（初始筛选，Boss 标准档位） -->
    <div>
      <label class="field-label">薪资范围 (K/月，可选)</label>
      <GlassSelect
        :model-value="salaryRangeValue"
        :options="SALARY_RANGE_OPTIONS"
        placeholder="不限"
        :disabled="engine.running"
        @update:model-value="(v) => (salaryRangeValue = v)"
      />
      <label v-if="salaryRangeValue !== '0-0'" class="flex items-center justify-between cursor-pointer mt-2 pl-0.5">
        <span class="text-xs text-fg-muted" title="允许局部重叠/交集的岗位入选，不限制网页搜索范围，仅在本地提取时过滤">
          薪资宽泛匹配
          <span class="text-[10px] text-fg-subtle block">(有交集即可，本地过滤)</span>
        </span>
        <GlassCheckbox
          v-model="engine.params.salary_fuzzy"
          :disabled="engine.running"
        />
      </label>
      <p class="text-[11px] text-fg-subtle mt-1">自动过滤；结果表可进一步筛选</p>
    </div>

    <!-- 工作性质 -->
    <div>
      <label class="field-label">工作性质 (可选)</label>
      <GlassSelect
        :model-value="engine.params.job_type"
        :options="JOB_TYPE_OPTIONS"
        placeholder="不限"
        :disabled="engine.running"
        @update:model-value="(v) => (engine.params.job_type = v)"
      />
    </div>

    <!-- 学历要求 -->
    <div>
      <label class="field-label">学历要求 (可选)</label>
      <GlassMultiSelect
        :model-value="selectedDegrees"
        label="学历"
        :options="DEGREE_OPTIONS"
        :filterable="false"
        :disabled="engine.running"
        @update:model-value="(v) => (selectedDegrees = v)"
      />
    </div>

    <!-- 工作经验 -->
    <div>
      <label class="field-label">工作经验 (可选)</label>
      <GlassMultiSelect
        :model-value="selectedExperience"
        label="经验"
        :options="EXPERIENCE_OPTIONS"
        :filterable="false"
        :disabled="engine.running"
        @update:model-value="(v) => (selectedExperience = v)"
      />
    </div>

    <!-- 浏览器 -->
    <div>
      <label class="field-label">浏览器</label>
      <GlassSelect
        :model-value="engine.params.browser_type"
        :options="browserOptions"
        :disabled="engine.running"
        @update:model-value="onBrowserChange"
      />
      <div class="flex items-center gap-1.5 mt-1">
        <input
          :value="engine.config?.browser_path || ''"
          type="text"
          placeholder="未检测到浏览器路径"
          class="input !py-1 !text-[11px]"
          :disabled="engine.running"
          @change="onBrowserPathChange"
        />
        <button
          type="button"
          class="btn-ghost !py-1 !px-2 text-[11px] shrink-0"
          title="清除当前自定义路径，恢复并自动检测系统默认安装位置"
          :disabled="engine.running"
          @click="resetBrowserPath"
        >
          自动检测
        </button>
        <button
          type="button"
          class="btn-ghost !py-1 !px-2 text-[11px] shrink-0"
          :disabled="engine.running"
          @click="pickBrowser"
        >
          浏览
        </button>
      </div>
    </div>

    <!-- 输出文件标记 + 同步开关 -->
    <div>
      <label class="field-label flex items-center justify-between">
        <span>输出文件名</span>
        <span class="flex items-center gap-1.5 text-[11px] text-fg-muted font-normal">
          同步配置
          <GlassCheckbox v-model="engine.params.tag_sync" :disabled="engine.running" />
        </span>
      </label>
      <input
        v-if="!engine.params.tag_sync"
        v-model="engine.params.tag"
        type="text"
        placeholder="不填则不加分隔名"
        class="input"
        :disabled="engine.running"
      />
      <input
        v-else
        :value="tagDisplay"
        type="text"
        class="input opacity-60"
        disabled
      />
    </div>

    <div class="flex flex-col gap-3.5 pt-1">
      <label class="flex items-center justify-between cursor-pointer">
        <span class="text-sm text-fg-muted">安全模式</span>
        <GlassCheckbox
          v-model="engine.params.safe_mode"
          :disabled="engine.running || engine.params.fast"
        />
      </label>
      <label class="flex items-center justify-between cursor-pointer">
        <span class="text-sm text-fg-muted">
          快速模式
          <span class="text-[11px] text-primary/70">(无人工延迟)</span>
        </span>
        <GlassCheckbox v-model="engine.params.fast" :disabled="engine.running" />
      </label>
      <label class="flex items-center justify-between cursor-pointer">
        <span class="text-sm text-fg-muted">强制启动新浏览器</span>
        <GlassCheckbox v-model="engine.params.new_chrome" :disabled="engine.running" />
      </label>
    </div>

    <!-- 输出目录 -->
    <div class="mt-auto pt-3 border-t border-bg-border">
      <label class="field-label">输出目录</label>
      <div class="flex items-center gap-1.5">
        <input
          :value="engine.config?.output_dir || ''"
          type="text"
          placeholder="-"
          class="input !py-1 !text-[11px]"
          :disabled="engine.running"
          @change="onOutputDirChange"
        />
        <button
          type="button"
          class="btn-ghost !py-1 !px-2 text-[11px] shrink-0"
          :disabled="engine.running"
          @click="pickFolder"
        >
          浏览
        </button>
      </div>
    </div>

    <!-- 确认重置弹窗 -->
    <GlassDialog
      v-model="showResetConfirm"
      icon="⚠️"
      title="还原默认设置"
      width="25rem"
    >
      <div class="text-sm text-fg-muted whitespace-pre-wrap leading-relaxed">
        确定要将所有运行配置还原为默认设置吗？此操作将清空当前的岗位搜索、城市等配置。
      </div>

      <template #footer>
        <div class="flex gap-2">
          <GlassButton variant="ghost" size="sm" @click="showResetConfirm = false">
            取消
          </GlassButton>
          <GlassButton variant="solid" size="sm" @click="confirmReset">
            确定重置
          </GlassButton>
        </div>
      </template>
    </GlassDialog>
  </aside>
</template>

<style scoped>
.text-danger {
  color: var(--danger);
}
.input-error {
  border-color: var(--danger) !important;
}
:deep(.gmulti-select) {
  display: block;
  width: 100%;
}
:deep(.gmulti-select__trigger) {
  width: 100%;
  padding: 0.55rem 0.85rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
}
:deep(.gmulti-select__panel) {
  right: 0;
  max-width: none;
}
</style>
