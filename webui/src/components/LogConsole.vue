<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useEngine, type LogEntry } from "@/stores/engine";

const engine = useEngine();
const scroller = ref<HTMLElement | null>(null);
const autoScroll = ref(true);
const copyState = ref<"idle" | "ok" | "err">("idle");
let copyTimer: number | null = null;

// 多任务时才出现「当前 / 全部」；单任务永远走「当前」分支，DOM 与原来一致
const scope = ref<"current" | "all">("current");

const displayLogs = computed<LogEntry[]>(() => {
  if (!engine.multiTask || scope.value === "current") return engine.logs;
  const merged: LogEntry[] = [];
  for (const id of engine.taskOrder) {
    const task = engine.tasks[id];
    if (task) merged.push(...task.logs);
  }
  merged.sort((a, b) => a.id - b.id);
  return merged;
});

const platformNames = computed<Record<string, string>>(() =>
  Object.fromEntries(engine.platforms.map((p) => [p.name, p.display_name || p.name]))
);

/** 「全部」视图给每行加平台前缀；单任务 / 当前视图保持原文。 */
function lineText(l: LogEntry): string {
  if (!engine.multiTask || scope.value !== "all") return l.msg;
  const platform = l.platform || engine.params.site;
  return `[${platformNames.value[platform] || platform}] ${l.msg}`;
}

function clearLogs() {
  if (!engine.multiTask || scope.value === "current") {
    engine.clearLogs(engine.activeTask?.taskId);
    return;
  }
  for (const id of engine.taskOrder) engine.clearLogs(id);
}

watch(
  () => displayLogs.value.length,
  async () => {
    if (!autoScroll.value) return;
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  }
);

function lineClass(level: string) {
  return (
    {
      error: "text-rose-500",
      warn: "text-amber-500",
      info: "text-fg-muted",
    } as Record<string, string>
  )[level] || "text-fg-muted";
}

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
}

// 复制全部日志到剪贴板：优先用 Clipboard API，pywebview 环境回退到 textarea + execCommand
async function copyAll() {
  const text = displayLogs.value
    .map((l) => lineText(l))
    .join("\n");
  if (!text) return;

  let ok = false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      ok = true;
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      ok = document.execCommand("copy");
      document.body.removeChild(ta);
    }
  } catch {
    ok = false;
  }

  copyState.value = ok ? "ok" : "err";
  if (copyTimer) window.clearTimeout(copyTimer);
  copyTimer = window.setTimeout(() => {
    copyState.value = "idle";
    copyTimer = null;
  }, 1500);
}

const copyLabel = {
  idle: "复制",
  ok: "已复制 ✓",
  err: "复制失败",
} as const;
</script>

<template>
  <div id="log-console-panel" class="card flex flex-col min-h-[480px] max-h-[calc(100dvh-var(--header-h)-16rem)] overflow-hidden">
    <div class="flex items-center justify-between px-4 py-2.5 border-b border-bg-border">
      <span class="text-sm font-semibold text-fg">实时日志</span>
      <div class="flex items-center gap-3">
        <div v-if="engine.multiTask" class="flex gap-0.5 bg-bg-base/60 border border-bg-border rounded-lg p-0.5">
          <button
            type="button"
            data-log-scope="current"
            class="px-2 py-0.5 rounded-md text-[11px] transition-colors"
            :class="scope === 'current' ? 'bg-brand text-bg-base font-medium' : 'text-fg-muted hover:text-fg'"
            @click="scope = 'current'"
          >
            当前
          </button>
          <button
            type="button"
            data-log-scope="all"
            class="px-2 py-0.5 rounded-md text-[11px] transition-colors"
            :class="scope === 'all' ? 'bg-brand text-bg-base font-medium' : 'text-fg-muted hover:text-fg'"
            @click="scope = 'all'"
          >
            全部
          </button>
        </div>
        <span class="text-[11px] text-fg-subtle">{{ displayLogs.length }} 行</span>
        <button
          class="text-[11px] text-fg-muted hover:text-fg disabled:opacity-40 disabled:hover:text-fg-muted"
          :class="copyState === 'ok' ? 'text-emerald-500' : copyState === 'err' ? 'text-rose-500' : ''"
          :disabled="!displayLogs.length"
          @click="copyAll"
        >
          {{ copyLabel[copyState] }}
        </button>
        <button
          class="text-[11px] text-fg-muted hover:text-fg disabled:opacity-40 disabled:hover:text-fg-muted"
          :disabled="!displayLogs.length"
          @click="clearLogs"
        >
          清空
        </button>
      </div>
    </div>
    <div
      ref="scroller"
      class="flex-1 min-h-0 overflow-y-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed select-text"
      @scroll="onScroll"
    >
      <div
        v-for="l in displayLogs"
        :key="l.id"
        class="whitespace-pre-wrap break-words animate-fade-in"
        :class="lineClass(l.level)"
      >{{ lineText(l) }}</div>
      <div v-if="!displayLogs.length" class="text-fg-subtle text-sm font-sans">
        暂无日志，点击「启动助手」后这里会实时滚动输出。
      </div>
    </div>
  </div>
</template>
