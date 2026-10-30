<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useEngine } from "@/stores/engine";

const engine = useEngine();
const scroller = ref<HTMLElement | null>(null);
const autoScroll = ref(true);
const copyState = ref<"idle" | "ok" | "err">("idle");
let copyTimer: number | null = null;

watch(
  () => engine.logs.length,
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
  const text = engine.logs
    .map((l) => l.msg)
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
        <span class="text-[11px] text-fg-subtle">{{ engine.logs.length }} 行</span>
        <button
          class="text-[11px] text-fg-muted hover:text-fg disabled:opacity-40 disabled:hover:text-fg-muted"
          :class="copyState === 'ok' ? 'text-emerald-500' : copyState === 'err' ? 'text-rose-500' : ''"
          :disabled="!engine.logs.length"
          @click="copyAll"
        >
          {{ copyLabel[copyState] }}
        </button>
        <button
          class="text-[11px] text-fg-muted hover:text-fg disabled:opacity-40 disabled:hover:text-fg-muted"
          :disabled="!engine.logs.length"
          @click="engine.logs = []"
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
        v-for="l in engine.logs"
        :key="l.id"
        class="whitespace-pre-wrap break-words animate-fade-in"
        :class="lineClass(l.level)"
      >{{ l.msg }}</div>
      <div v-if="!engine.logs.length" class="text-fg-subtle text-sm font-sans">
        暂无日志，点击「启动助手」后这里会实时滚动输出。
      </div>
    </div>
  </div>
</template>
