<script setup lang="ts">
import { computed } from "vue";
import { useEngine } from "@/stores/engine";
import { useLocalStorage } from "@/composables/useLocalStorage";

defineProps<{
  tab: "logs" | "results";
}>();

const emit = defineEmits<{
  (e: "update:tab", v: "logs" | "results"): void;
}>();

const engine = useEngine();

const statsCollapsed = useLocalStorage<boolean>(
  "boss:stats-collapsed",
  true,
  { validator: (v): v is boolean => typeof v === "boolean" }
);

const stats = computed(() => engine.progress.stats || {});

const stateColor = computed(
  () =>
    ({
      idle: "bg-fg-subtle",
      running: "bg-brand animate-pulse-ring",
      paused: "bg-amber-500 animate-pulse-ring",
      waiting: "bg-amber-500 animate-pulse-ring",
      done: "bg-emerald-500",
      stopped: "bg-fg-subtle",
      error: "bg-rose-500",
    } as Record<string, string>)[engine.state] || "bg-fg-subtle"
);

const metrics = [
  { k: "success", label: "成功", cls: "text-emerald-500" },
  { k: "fail", label: "失败", cls: "text-rose-500" },
  { k: "skip", label: "跳过", cls: "text-fg-muted" },
  { k: "vue_hit", label: "Vue直读", cls: "text-fg" },
];
</script>

<template>
  <div id="control-bar-main" class="card py-2.5 px-4 relative overflow-hidden">
    <div class="flex items-center gap-4 flex-wrap sm:flex-nowrap">
      <!-- Tab 切换栏 -->
      <div id="tab-bar" class="flex gap-0.5 bg-bg-base/60 border border-bg-border rounded-lg p-0.5 shrink-0">
        <button
          type="button"
          class="px-3 py-1 rounded-md text-xs transition-colors"
          :class="tab === 'logs' ? 'bg-brand text-bg-base font-medium' : 'text-fg-muted hover:text-fg'"
          @click="emit('update:tab', 'logs')"
        >
          实时日志
        </button>
        <button
          type="button"
          class="px-3 py-1 rounded-md text-xs transition-colors"
          :class="tab === 'results' ? 'bg-brand text-bg-base font-medium' : 'text-fg-muted hover:text-fg'"
          @click="emit('update:tab', 'results'); engine.loadResults()"
        >
          岗位列表
        </button>
      </div>

      <!-- 运行状态与进度文字 -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-2 h-2 rounded-full" :class="stateColor"></span>
        <span class="font-medium text-fg-muted">
          {{ engine.statusLabel }}
          <span v-if="engine.running && engine.progress.total > 0" class="text-fg-subtle ml-1">
            ({{ engine.progress.done }} / {{ engine.progress.total }})
          </span>
        </span>
        <span
          v-if="engine.running && engine.seamlessMode"
          class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-medium"
        >
          无缝续接中
        </span>
        <span
          v-if="!engine.wsConnected && engine.running"
          class="text-[11px] text-amber-500"
          >· 重连中</span
        >
      </div>

      <div class="flex-1 min-w-0"></div>

      <!-- 展开统计按钮 -->
      <button
        type="button"
        class="w-7 h-7 rounded-full flex items-center justify-center transition-fast bg-white/5 hover:bg-white/10 text-fg-muted hover:text-fg"
        :title="statsCollapsed ? '展开统计' : '折叠统计'"
        :aria-label="statsCollapsed ? '展开统计' : '折叠统计'"
        :aria-expanded="!statsCollapsed"
        @click="statsCollapsed = !statsCollapsed"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
          class="transition-transform duration-200"
          :class="statsCollapsed ? 'rotate-180' : ''"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      <!-- 采集操作按钮 -->
      <!-- 暂停 / 继续（仅运行中可见） -->
      <template v-if="engine.running && engine.state !== 'paused'">
        <button
          v-if="engine.pausing"
          class="btn-ghost !py-1 !px-2.5 text-xs opacity-60 cursor-not-allowed"
          disabled
        >
          暂停中…
        </button>
        <button
          v-else
          class="btn-ghost !py-1 !px-2.5 text-xs"
          :disabled="!engine.running"
          title="暂停采集，可稍后继续"
          @click="engine.pause()"
        >
          ⏸ 暂停
        </button>
      </template>

      <!-- 继续（暂停时可见） -->
      <button
        v-if="engine.state === 'paused'"
        class="btn-primary !py-1 !px-2.5 text-xs"
        title="继续采集"
        @click="engine.resume()"
      >
        ▶ 继续
      </button>

      <!-- 停止（运行中或暂停时可见） -->
      <button
        v-if="engine.running || engine.state === 'paused'"
        class="btn-danger !py-1 !px-2.5 text-xs"
        :disabled="engine.stopping"
        :class="{ 'opacity-60 cursor-not-allowed': engine.stopping }"
        @click="engine.stop()"
      >
        {{ engine.stopping ? '■ 停止中…' : '■ 停止' }}
      </button>

      <!-- 启动（仅空闲时可见） -->
      <button
        id="start-btn"
        v-if="!engine.running && engine.state !== 'paused'"
        class="btn-primary !py-1 !px-2.5 text-xs"
        :disabled="!engine.canStart"
        :title="
          engine.params.keyword_search && !engine.params.query?.trim()
            ? '请先输入搜索关键词'
            : ''
        "
        @click="engine.start()"
      >
        ▶ 启动助手
      </button>
    </div>

    <!-- Slim 贴底极简进度条 -->
    <div v-if="engine.running" class="absolute bottom-0 left-0 right-0 h-[2px] bg-bg-raised/40 overflow-hidden">
      <div
        class="h-full bg-brand rounded-full transition-all duration-500"
        :style="{ width: engine.percent + '%' }"
      ></div>
    </div>

    <!-- 统计区：可折叠 -->
    <div
      class="grid transition-all duration-300 ease-out"
      :class="statsCollapsed
        ? 'grid-rows-[0fr] opacity-0 mt-0'
        : 'grid-rows-[1fr] opacity-100 mt-3'"
    >
      <div class="overflow-hidden">
        <div class="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-3 pt-3 border-t border-bg-border/40">
          <div v-for="m in metrics" :key="m.k" class="tile px-3 py-1.5 text-center">
            <div class="text-base font-semibold" :class="m.cls">{{ stats[m.k] || 0 }}</div>
            <div class="text-[10px] text-fg-subtle">{{ m.label }}</div>
          </div>
        </div>
        <p v-if="engine.errorMsg" class="mt-2.5 text-xs text-rose-500">{{ engine.errorMsg }}</p>
      </div>
    </div>
  </div>
</template>
