<script setup lang="ts">
import { ref, watch, nextTick, computed } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    targetEl?: HTMLElement | null;
    bubblePosition?: Record<string, string | number>;
    highlightStyle?: Record<string, string | number>;
    theme?: {
      borderColor?: string;
      glowColor?: string;
      innerGlowColor?: string;
      pulseColor?: string;
    };
    padding?: number;
    transitionDuration?: number;
    showPulse?: boolean;
  }>(),
  {
    padding: 8,
    transitionDuration: 300,
    showPulse: true,
  }
);

const emit = defineEmits<{
  "update:modelValue": [val: boolean];
}>();

// ── 主题默认值 ──────────────────────────────────────────────
const brandRgb = "59 130 246";
// 紫粉 + 青色渐变主题
const purpleCyanRgb = "186 66 255";
const cyanRgb = "0 225 255";

const resolved = computed(
  () => ({
    borderColor: props.theme?.borderColor ?? `rgb(${purpleCyanRgb})`,
    glowColor: props.theme?.glowColor ?? `rgba(${purpleCyanRgb}, 0.5)`,
    innerGlowColor: props.theme?.innerGlowColor ?? `rgba(${purpleCyanRgb}, 0.15)`,
    pulseColor: props.theme?.pulseColor ?? `rgba(${cyanRgb}, 0.7)`,
  })
);

const highlightStyle = ref<Record<string, string | number>>({});
const borderRadius = ref("12px");

const updateHighlight = () => {
  if (!props.modelValue || !props.targetEl) {
    highlightStyle.value = {};
    return;
  }
  const rect = props.targetEl.getBoundingClientRect();
  const p = props.padding ?? 8;
  
  // 安全获取目标的 border-radius，避免简写属性在部分浏览器返回空字符串的问题
  let targetRadius = "";
  try {
    const computedStyle = window.getComputedStyle(props.targetEl);
    targetRadius = computedStyle.borderRadius || computedStyle.borderTopLeftRadius || "";
  } catch (e) {
    console.error("Failed to getComputedStyle for targetEl:", e);
  }

  if (targetRadius && targetRadius !== "0px" && targetRadius !== "0") {
    // 匹配如 "8px" 这种单一数值
    const match = targetRadius.trim().match(/^(\d+(?:\.\d+)?)(px)$/);
    if (match) {
      const val = parseFloat(match[1]);
      borderRadius.value = `${val + p}px`;
    } else {
      borderRadius.value = targetRadius;
    }
  } else {
    borderRadius.value = "12px";
  }

  highlightStyle.value = {
    top: `${rect.top - p}px`,
    left: `${rect.left - p}px`,
    width: `${rect.width + p * 2}px`,
    height: `${rect.height + p * 2}px`,
  };
};

const mergedHighlightStyle = computed(
  () => ({
    ...highlightStyle.value,
    ...(props.highlightStyle ?? {}),
  })
);

const spotlightStyleCombined = computed(() => ({
  ...mergedHighlightStyle.value,
  borderRadius: borderRadius.value,
}));

// ── 监听 & 生命周期 ─────────────────────────────────────────
watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      nextTick(() => {
        requestAnimationFrame(() => updateHighlight());
      });
    }
  }
);

watch(
  () => props.targetEl,
  () => {
    if (props.modelValue) {
      nextTick(() => {
        requestAnimationFrame(() => updateHighlight());
      });
    }
  }
);

const resizeObserver = ref<ResizeObserver | null>(null);

const stopObserve = () => {
  if (resizeObserver.value) {
    resizeObserver.value.disconnect();
    resizeObserver.value = null;
  }
};

const startObserve = () => {
  stopObserve();
  if (!props.targetEl) return;
  resizeObserver.value = new ResizeObserver(() => {
    requestAnimationFrame(() => updateHighlight());
  });
  resizeObserver.value.observe(props.targetEl);
};

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      nextTick(() => startObserve());
    } else {
      stopObserve();
    }
  }
);

watch(
  () => props.targetEl,
  (el) => {
    if (props.modelValue) {
      nextTick(() => {
        if (el) startObserve();
        else stopObserve();
      });
    }
  }
);

const onGlobalUpdate = () => {
  if (props.modelValue) {
    requestAnimationFrame(() => updateHighlight());
  }
};

import { onMounted, onUnmounted } from "vue";

onMounted(() => {
  window.addEventListener("resize", onGlobalUpdate);
  window.addEventListener("scroll", onGlobalUpdate, true);
});

onUnmounted(() => {
  window.removeEventListener("resize", onGlobalUpdate);
  window.removeEventListener("scroll", onGlobalUpdate, true);
  stopObserve();
});

// ── 关闭 ────────────────────────────────────────────────────
const handleClose = () => emit("update:modelValue", false);

// ── 暴露方法 ────────────────────────────────────────────────
const updatePosition = () => updateHighlight();
defineExpose({ updatePosition });

// ── Slots ───────────────────────────────────────────────────
const slots = defineSlots<{
  default?: () => unknown;
  overlay?: (props: {
    highlightStyle: Record<string, string | number>;
    bubblePosition: Record<string, string | number>;
    resolved: {
      borderColor: string;
      glowColor: string;
      innerGlowColor: string;
      pulseColor: string;
    };
    showPulse: boolean;
    transitionDuration: number;
    handleClose: () => void;
  }) => unknown;
}>();
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue" class="fixed inset-0 z-[9995] pointer-events-none">
      <!-- 自定义 overlay 插槽 -->
      <slot
        v-if="$slots.overlay"
        name="overlay"
        :highlight-style="mergedHighlightStyle"
        :bubble-position="bubblePosition ?? {}"
        :resolved="resolved"
        :show-pulse="showPulse"
        :transition-duration="transitionDuration"
        :handle-close="handleClose"
      />

      <!-- 默认渲染：描边 + 光晕高亮框 -->
      <template v-else>
        <div
          class="absolute pointer-events-none highlight-glow-box"
          :style="{
            ...spotlightStyleCombined,
            transition: transitionDuration > 0
              ? `top ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1), left ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1), width ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1), height ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1)`
              : 'none',
          }"
        >
          <div class="highlight-border-flow"></div>
          <div
            v-if="showPulse"
            class="absolute inset-0 rounded-[inherit] pointer-events-none animate-pulse-ring"
          ></div>
        </div>

        <slot name="default" />
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.highlight-glow-box {
  box-shadow: 0px -5px 25px 0px rgba(186, 66, 255, 0.5), 0px 5px 25px 0px rgba(0, 225, 255, 0.5);
  background: transparent;
}

.highlight-border-flow {
  position: absolute;
  inset: -2px;
  border-radius: inherit;
  padding: 2px;
  background-image: conic-gradient(
    from var(--angle),
    rgb(186, 66, 255) 0%,
    rgb(0, 225, 255) 25%,
    rgb(186, 66, 255) 50%,
    rgb(0, 225, 255) 75%,
    rgb(186, 66, 255) 100%
  );
  animation: spinning82341 2.5s linear infinite;
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  -webkit-mask-composite: xor;
}

@property --angle {
  syntax: '<angle>';
  initial-value: 0deg;
  inherits: false;
}

@keyframes spinning82341 {
  0% {
    --angle: 0deg;
  }
  100% {
    --angle: 360deg;
  }
}

@keyframes pulse-ring {
  0% {
    box-shadow: 0 0 0 0 rgba(186, 66, 255, 0.4);
  }
  70% {
    box-shadow: 0 0 0 12px rgba(0, 225, 255, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(0, 225, 255, 0);
  }
}

.animate-pulse-ring {
  animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>

