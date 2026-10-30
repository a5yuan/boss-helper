<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useEngine } from "@/stores/engine";
import { useTheme } from "@/ui/theme";
import ConfigPanel from "@/components/ConfigPanel.vue";
import CollapsedConfigPanel from "@/components/CollapsedConfigPanel.vue";
import ControlBar from "@/components/ControlBar.vue";
import LogConsole from "@/components/LogConsole.vue";
import ResultTable from "@/components/ResultTable";
import ActionDialog from "@/components/ActionDialog.vue";
import OnboardingTour from "@/components/OnboardingTour.vue";

const engine = useEngine();
const { mode, toggle } = useTheme();
const tab = ref<"logs" | "results">("logs");
const showTour = ref(false);

// 是否折叠配置面板
const configCollapsed = ref(false);

// 左侧面板宽度（像素），由展开时的默认比例初始化
const leftPanelWidth = ref(0);

// 拖拽状态（模块级 ref，避免闭包问题）
let isDragging = false;
let dragStartX = 0;
let dragStartWidth = 0;

const onDragStart = (e: MouseEvent) => {
  isDragging = true;
  dragStartX = e.clientX;
  dragStartWidth = leftPanelWidth.value;
  document.addEventListener("mousemove", onDragMove);
  document.addEventListener("mouseup", onDragEnd);
};

const onDragMove = (e: MouseEvent) => {
  if (!isDragging) return;
  const container = document.getElementById("main-split-container");
  if (!container) return;
  const containerWidth = container.offsetWidth;
  const delta = e.clientX - dragStartX;
  const newWidth = dragStartWidth + delta;
  const minPx = Math.round(containerWidth * 0.10);
  const maxPx = Math.round(containerWidth * 0.50);
  leftPanelWidth.value = Math.max(minPx, Math.min(maxPx, newWidth));
};

const onDragEnd = () => {
  isDragging = false;
  document.removeEventListener("mousemove", onDragMove);
  document.removeEventListener("mouseup", onDragEnd);
};

const getDefaultWidthPx = () => {
  const w = window.innerWidth;
  const pct = w < 1024 ? 38 : w < 1280 ? 32 : 28;
  return Math.round((window.document.getElementById("main-split-container")?.offsetWidth ?? window.innerWidth) * pct / 100);
};

const onCollapse = () => {
  configCollapsed.value = true;
};

const onExpand = () => {
  configCollapsed.value = false;
};

onMounted(async () => {
  await engine.loadConfig();
  engine.connectWs();
  if (engine.running) engine.state = "running";
  leftPanelWidth.value = getDefaultWidthPx();
  
  const completed = localStorage.getItem("boss-helper:onboarding-completed");
  if (completed !== "true" && !engine.params.onboarding_completed) {
    showTour.value = true;
  }
});
</script>

<template>
  <div class="h-screen flex flex-col">
    <header v-if="!engine.isFullscreen" class="flex items-center gap-3 px-6 py-3.5 border-b border-bg-border bg-bg-panel">
      <div class="w-8 h-8 rounded-xl bg-bg-raised border border-bg-border flex items-center justify-center text-fg font-bold">B</div>
      <div>
        <h1 class="text-base font-semibold text-fg leading-tight">BOSS 直聘助手</h1>
      </div>
      <div class="flex-1"></div>
      <button
        class="w-8 h-8 rounded-full border border-bg-border text-fg-muted hover:text-fg hover:bg-bg-raised transition-colors flex items-center justify-center shrink-0"
        title="使用引导"
        aria-label="使用引导"
        @click="showTour = true"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </button>
      <button
        class="text-[12px] px-3 py-1.5 rounded-full border border-bg-border text-fg-muted hover:text-fg transition-colors"
        @click="toggle"
      >
        {{ mode === "light" ? "深色" : "浅色" }}
      </button>
      <span
        class="text-[11px] px-2.5 py-1 rounded-full"
        :class="engine.wsConnected ? 'bg-emerald-500/15 text-emerald-500' : 'bg-bg-raised text-fg-subtle'"
      >
        {{ engine.wsConnected ? "● 已连接" : "○ 未连接" }}
      </span>
    </header>

    <main class="flex-1 min-h-0 overflow-hidden">
      <div id="main-split-container" class="flex h-full w-full">
        <!-- 左侧配置面板 -->
        <div
          v-if="!engine.isFullscreen"
          :style="{ flex: `0 0 ${configCollapsed ? '4%' : leftPanelWidth + 'px'}` }"
          class="flex flex-col overflow-hidden pl-4 py-4"
        >
          <ConfigPanel v-show="!configCollapsed" class="h-full" @collapse="onCollapse" />
          <CollapsedConfigPanel v-show="configCollapsed" class="h-full" @expand="onExpand" />
        </div>

        <!-- 拖拽手柄（仅展开且非全屏时显示） -->
        <div
          v-if="!configCollapsed && !engine.isFullscreen"
          class="group relative flex w-2 items-center justify-center hover:bg-brand/10 transition-colors cursor-col-resize"
          @mousedown.prevent="onDragStart"
        >
          <div class="flex h-10 w-1 rounded-full bg-border group-hover:bg-brand/50 transition-colors" />
        </div>

        <!-- 右侧主内容区 -->
        <div class="flex flex-1 flex-col overflow-hidden min-w-0">
          <section
            class="flex flex-col min-w-0 overflow-hidden flex-1 min-h-0"
            :class="engine.isFullscreen ? 'p-1.5 gap-0' : 'p-4 gap-4'"
          >
            <ControlBar v-if="!engine.isFullscreen" v-model:tab="tab" />

            <div class="flex-1 min-h-0 flex flex-col">
              <LogConsole v-show="tab === 'logs'" />
              <ResultTable v-show="tab === 'results'" />
            </div>
          </section>
        </div>
      </div>
    </main>

    <ActionDialog />
    <OnboardingTour v-model="showTour" @update:tab="tab = $event" />
  </div>
</template>
