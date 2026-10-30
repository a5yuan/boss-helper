<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import { GlassSpotlight2 } from "@/ui/components/highlight";
import { GlassButton } from "@/ui/components/button";
import { GlassCard } from "@/ui/components/card";
import { GlassTag } from "@/ui/components/tag";
import { useEngine } from "@/stores/engine";

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "update:tab", v: "logs" | "results"): void;
}>();

const currentStep = ref(0);

type Placement = "right" | "left" | "top" | "bottom";

interface TourStep {
  title: string;
  desc: string;
  target: string | null;
  position: Placement | "center";
}

const steps: TourStep[] = [
  {
    title: "欢迎使用 BOSS 直聘助手 👋",
    desc: "这是一款轻量、安全、且免去任何代码环境配置的桌面岗位分析整理工具。\n\n只需简单点击几下，即可自动化收集、整理及本地筛选你感兴趣的岗位。让我们用 1 分钟快速熟悉它的使用吧！",
    target: null,
    position: "center",
  },
  {
    title: "⚙️ 运行参数配置",
    desc: "在这里，你可以自定义你需要采集的岗位数量、薪资范围、使用的浏览器路径，以及设置最终保存结果的输出目录（默认输出到桌面）。",
    target: "#config-panel",
    position: "right",
  },
  {
    title: "🔄 自动与手动模式切换",
    desc: "【开启关键词】输入关键词和城市后，助手将全自动跳转检索；\n\n【关闭关键词】进入完全手动模式。你需要在 boss 页面自行搜索，确认页面是你想采集的数据后，再回到 APP 点击「开始提取」，助手才会开始阅读当前页面。同样支持防漏重和「无缝续接」。",
    target: "#keyword-search-card",
    position: "right",
  },
  {
    title: "🚀 一键启动助手",
    desc: "一切配置就绪后，点击此处的「启动助手」按钮。这会拉起一个干净受控的 Chrome/Edge 浏览器窗口。\n\n【首次启动】需要你在这个浏览器内扫码登录一次，之后再运行可完美自动复用登录态！",
    target: "#start-btn",
    position: "bottom",
  },
  {
    title: "📊 运行控制与实时日志",
    desc: "点击这里可以在「实时日志」与「岗位列表」之间自如切换。启动后在这里会打印每一条岗位的整理进度。这里也是你暂停、继续或停止整个数据整理的核心控制中心。",
    target: "#control-bar-main",
    position: "bottom",
  },
  {
    title: "📂 结果查看、筛选与导出",
    desc: "数据整理完毕后，切换到「岗位列表」Tab，你可以看到所有整理好的记录，通过我们优化后的极简「筛选」按钮可以进行多重秒级本地过滤，并一键导出为 Excel/Markdown。",
    target: "#result-table-panel",
    position: "top",
  },
];

// ── GlassSpotlight 的气泡 ref ─────────────────────────────
const bubbleEl = ref<HTMLElement | null>(null);
const spotlightRef = ref<InstanceType<typeof GlassSpotlight2> | null>(null);

// ── 当前目标 DOM 元素 ───────────────────────────────────────
const currentTargetEl = ref<HTMLElement | null>(null);
const transitionDuration = ref(150);

// ── 气泡位置计算 ────────────────────────────────────────────
const bubbleStyle = ref<Record<string, string | number>>({});

const measureBubble = () => {
  if (!bubbleEl.value) return { w: 350, h: 200 };
  const r = bubbleEl.value.getBoundingClientRect();
  return { w: r.width || 350, h: r.height || 200 };
};

const scrollIntoViewIfNeeded = (el: HTMLElement) => {
  const rect = el.getBoundingClientRect();
  const viewportH = window.innerHeight;
  const viewportW = window.innerWidth;
  const margin = 80;
  if (
    rect.top < margin ||
    rect.bottom > viewportH - margin ||
    rect.left < 0 ||
    rect.right > viewportW
  ) {
    el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  }
};

const updateBubblePosition = () => {
  if (!props.modelValue) return;
  const step = steps[currentStep.value];
  if (!step) return;

  // 居中步骤（欢迎页）
  if (!step.target) {
    bubbleStyle.value = {
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
    };
    return;
  }

  const el = document.querySelector(step.target) as HTMLElement | null;
  if (!el) return;

  currentTargetEl.value = el;
  scrollIntoViewIfNeeded(el);

  const rect = el.getBoundingClientRect();
  const offset = 8;
  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;
  const padding = 16;
  const gap = 16;
  const { w: bubbleW, h: bubbleH } = measureBubble();

  const spaceRight = viewportW - rect.right - offset - gap - padding;
  const spaceLeft = rect.left - offset - gap - padding;
  const spaceBottom = viewportH - rect.bottom - offset - gap - padding;
  const spaceTop = rect.top - offset - gap - padding;

  const preferred = step.position === "center" ? "right" : step.position;
  const candidates: { placement: Placement; fits: boolean; space: number }[] = (
    ["right", "left", "bottom", "top"] as Placement[]
  ).map((p) => {
    const needW = p === "left" || p === "right";
    const need = needW ? bubbleW : bubbleH;
    const space =
      p === "right"
        ? spaceRight
        : p === "left"
        ? spaceLeft
        : p === "bottom"
        ? spaceBottom
        : spaceTop;
    return { placement: p, fits: space >= need, space };
  });

  let chosen = candidates.find((c) => c.placement === preferred && c.fits);
  if (!chosen) {
    const fits = candidates.filter((c) => c.fits);
    chosen = fits.length
      ? fits.reduce((a, b) => (a.space > b.space ? a : b))
      : candidates.reduce((a, b) => (a.space > b.space ? a : b));
  }

  const placement = chosen.placement;
  let top = 0;
  let left = 0;
  let transform = "none";

  if (placement === "right") {
    top = rect.top + rect.height / 2;
    left = rect.right + offset + gap;
    transform = "translateY(-50%)";
  } else if (placement === "left") {
    top = rect.top + rect.height / 2;
    left = rect.left - offset - gap;
    transform = "translate(-100%, -50%)";
  } else if (placement === "top") {
    top = rect.top - offset - gap;
    left = rect.left + rect.width / 2;
    transform = "translate(-50%, -100%)";
  } else {
    top = rect.bottom + offset + gap;
    left = rect.left + rect.width / 2;
    transform = "translate(-50%, 0)";
  }

  let topPx = top;
  let leftPx = left;
  if (placement === "left" || placement === "right") {
    const minTop = padding;
    const maxTop = viewportH - bubbleH - padding;
    topPx = Math.max(minTop, Math.min(maxTop, topPx));
  } else {
    const minLeft = bubbleW / 2 + padding;
    const maxLeft = viewportW - bubbleW / 2 - padding;
    leftPx = Math.max(minLeft, Math.min(maxLeft, leftPx));
  }

  bubbleStyle.value = {
    top: `${topPx}px`,
    left: `${leftPx}px`,
    transform,
  };
};

// ── 步骤切换时触发气泡位置更新 ─────────────────────────────
watch(currentStep, (newStep, oldStep) => {
  if (newStep === 4 || oldStep === 4) {
    transitionDuration.value = 0;
  } else {
    transitionDuration.value = 150;
  }
  nextTick(() => {
    if (currentStep.value === 5) {
      emit("update:tab", "results");
      setTimeout(() => {
        requestAnimationFrame(() => updateBubblePosition());
      }, 150);
    } else {
      requestAnimationFrame(() => updateBubblePosition());
    }
  });
});

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      currentStep.value = 0;
      nextTick(() => {
        requestAnimationFrame(() => {
          updateBubblePosition();
        });
      });
    }
  }
);

// ── 按钮逻辑 ────────────────────────────────────────────────
const handleNext = () => {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++;
  } else {
    handleClose();
  }
};

const handlePrev = () => {
  if (currentStep.value > 0) {
    currentStep.value--;
  }
};

const handleClose = () => {
  emit("update:modelValue", false);
  localStorage.setItem("boss-helper:onboarding-completed", "true");
  const engine = useEngine();
  engine.params.onboarding_completed = true;
};
</script>

<template>
  <GlassSpotlight2
    ref="spotlightRef"
    :model-value="modelValue"
    :target-el="currentTargetEl"
    :bubble-position="bubbleStyle"
    :show-pulse="true"
    :padding="8"
    :transition-duration="transitionDuration"
    glow-size="auto"
  >
    <!-- 默认气泡插槽 -->
    <div
      v-if="modelValue && steps[currentStep]?.target !== null"
      ref="bubbleEl"
      class="absolute w-[350px] max-w-[calc(100vw-32px)] z-[9997] flex pointer-events-auto"
      :class="transitionDuration > 0 ? 'transition-all duration-300 ease-out' : ''"
      :style="bubbleStyle"
    >
      <GlassCard padded class="flex flex-col gap-4 w-full !p-5 dark-tour-card">
        <div class="flex items-center justify-between">
          <GlassTag variant="brand">
            步骤 {{ currentStep + 1 }} / {{ steps.length }}
          </GlassTag>
          <GlassButton variant="ghost" size="sm" @click="handleClose">
            跳过指引
          </GlassButton>
        </div>

        <div class="flex flex-col gap-2">
          <h3 class="text-base font-bold text-fg leading-snug">
            {{ steps[currentStep].title }}
          </h3>
          <p class="text-sm text-fg-muted whitespace-pre-wrap leading-relaxed">
            {{ steps[currentStep].desc }}
          </p>
        </div>

        <div class="flex items-center justify-between mt-2 pt-3 border-t border-bg-border/30">
          <div class="flex gap-1.5">
            <GlassButton
              v-if="currentStep > 0"
              variant="ghost"
              size="sm"
              @click="handlePrev"
            >
              上一步
            </GlassButton>
          </div>
          <GlassButton variant="solid" size="sm" @click="handleNext">
            {{ currentStep === steps.length - 1 ? "完成开启" : "下一步" }}
          </GlassButton>
        </div>
      </GlassCard>
    </div>

    <!-- 欢迎页气泡（居中，无 target） -->
    <div
      v-else-if="modelValue"
      class="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[420px] max-w-[calc(100vw-32px)] z-[9997] flex pointer-events-auto"
    >
      <GlassCard padded class="flex flex-col gap-5 w-full !p-6 dark-tour-card">
        <div class="flex items-center justify-between">
          <GlassTag variant="brand">
            步骤 {{ currentStep + 1 }} / {{ steps.length }}
          </GlassTag>
          <GlassButton variant="ghost" size="sm" @click="handleClose">
            跳过指引
          </GlassButton>
        </div>

        <div class="flex flex-col gap-2">
          <h3 class="text-lg font-bold text-fg leading-snug">
            {{ steps[currentStep].title }}
          </h3>
          <p class="text-sm text-fg-muted whitespace-pre-wrap leading-relaxed">
            {{ steps[currentStep].desc }}
          </p>
        </div>

        <div class="flex justify-end mt-2 pt-3 border-t border-bg-border/30">
          <GlassButton variant="solid" size="sm" @click="handleNext">
            {{ currentStep === steps.length - 1 ? "完成开启" : "下一步" }}
          </GlassButton>
        </div>
      </GlassCard>
    </div>
  </GlassSpotlight2>
</template>

<style scoped>
/* 浅色主题模式下：新手指引卡片反色显示为“深色毛玻璃外观” */
html:not(.dark) .dark-tour-card {
  --fg: rgba(255, 255, 255, 0.95);
  --fg-muted: rgba(255, 255, 255, 0.6);
  --fg-subtle: rgba(255, 255, 255, 0.38);

  --accent: #ffffff;
  --accent-fg: #0a0a0b;

  --btn-solid-bg: var(--accent);
  --btn-solid-fg: var(--accent-fg);
  --btn-solid-bg-hover: rgba(255, 255, 255, 0.9);
  --btn-solid-fg-hover: var(--accent-fg);

  --glass-bg: rgba(255, 255, 255, 0.045);
  --glass-bg-hover: rgba(255, 255, 255, 0.08);
  --glass-bg-active: rgba(255, 255, 255, 0.12);
  --glass-border: rgba(255, 255, 255, 0.12);
  --glass-border-hover: rgba(255, 255, 255, 0.2);
  --glass-highlight: rgba(255, 255, 255, 0.14);
  --glass-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.6);

  background: rgba(20, 20, 24, 0.96) !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  backdrop-filter: blur(20px) saturate(160%) !important;
  -webkit-backdrop-filter: blur(20px) saturate(160%) !important;
  box-shadow: 
    0 12px 40px rgba(0, 0, 0, 0.6), 
    inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
}

/* 深色主题模式下：新手指引卡片反色显示为“浅色毛玻璃外观”，保证强对比度 */
html.dark .dark-tour-card {
  --fg: rgba(17, 17, 19, 0.96);
  --fg-muted: rgba(17, 17, 19, 0.58);
  --fg-subtle: rgba(17, 17, 19, 0.4);

  --accent: #18181b;
  --accent-fg: #ffffff;

  --btn-solid-bg: var(--accent);
  --btn-solid-fg: var(--accent-fg);
  --btn-solid-bg-hover: var(--accent-fg);
  --btn-solid-fg-hover: var(--accent);

  --glass-bg: rgba(255, 255, 255, 0.55);
  --glass-bg-hover: rgba(255, 255, 255, 0.72);
  --glass-bg-active: rgba(255, 255, 255, 0.9);
  --glass-border: rgba(17, 17, 19, 0.08);
  --glass-border-hover: rgba(17, 17, 19, 0.16);
  --glass-highlight: rgba(255, 255, 255, 0.75);
  --glass-shadow: 0 12px 32px -14px rgba(17, 17, 19, 0.22);

  background: rgba(255, 255, 255, 0.96) !important;
  border: 1px solid rgba(17, 17, 19, 0.12) !important;
  backdrop-filter: blur(20px) saturate(160%) !important;
  -webkit-backdrop-filter: blur(20px) saturate(160%) !important;
  box-shadow: 
    0 12px 40px rgba(17, 17, 19, 0.12), 
    inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
}

.dark-tour-card :deep(.border-t) {
  border-color: rgba(255, 255, 255, 0.1) !important;
}
</style>

