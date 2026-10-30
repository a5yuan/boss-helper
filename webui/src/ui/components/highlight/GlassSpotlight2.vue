<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onUnmounted } from "vue";

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
    glowSize?: "thin" | "md" | "lg" | "auto";
  }>(),
  {
    padding: 8,
    transitionDuration: 300,
    showPulse: true,
    glowSize: "auto",
  }
);

const emit = defineEmits<{
  "update:modelValue": [val: boolean];
}>();

const highlightStyle = ref<Record<string, string | number>>({});
const borderRadius = ref("10px");
const autoGlowSize = ref<"thin" | "md" | "lg">("thin");

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
    const match = targetRadius.trim().match(/^(\d+(?:\.\d+)?)(px)$/);
    if (match) {
      const val = parseFloat(match[1]);
      borderRadius.value = `${val + p}px`;
    } else {
      borderRadius.value = targetRadius;
    }
  } else {
    borderRadius.value = "10px";
  }

  // 智能自动计算光效厚度等级
  if (rect.width > 300 || rect.height > 150) {
    autoGlowSize.value = "thin";
  } else {
    autoGlowSize.value = "md";
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

const sizeConfig = computed(() => {
  let size = props.glowSize ?? "auto";
  if (size === "auto") {
    size = autoGlowSize.value;
  }
  if (size === "thin") {
    return {
      inset: "-2px",
      padding: "2px",
      blurFilter: "none",
      spread: "0px",
    };
  } else if (size === "md") {
    return {
      inset: "-4px",
      padding: "4px",
      blurFilter: "blur(2px)",
      spread: "1px",
    };
  } else {
    return {
      inset: "-12px",
      padding: "12px",
      blurFilter: "blur(8px)",
      spread: "4px",
    };
  }
});

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

onMounted(() => {
  window.addEventListener("resize", onGlobalUpdate);
  window.addEventListener("scroll", onGlobalUpdate, true);
});

onUnmounted(() => {
  window.removeEventListener("resize", onGlobalUpdate);
  window.removeEventListener("scroll", onGlobalUpdate, true);
  stopObserve();
});

const handleClose = () => emit("update:modelValue", false);
const updatePosition = () => updateHighlight();
defineExpose({ updatePosition });
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
        :show-pulse="showPulse"
        :transition-duration="transitionDuration"
        :handle-close="handleClose"
      />

      <!-- 默认渲染：光效2 (Uiverse 旋转霓虹渐变 + 柔和毛玻璃描边) -->
      <template v-else>
        <div
          class="absolute pointer-events-none highlight-glow-box-v2"
          :style="{
            ...spotlightStyleCombined,
            '--glow-inset': sizeConfig.inset,
            '--glow-padding': sizeConfig.padding,
            '--glow-blur-filter': sizeConfig.blurFilter,
            '--glow-spread': sizeConfig.spread,
            transition: transitionDuration > 0
              ? `top ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1), left ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1), width ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1), height ${transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1)`
              : 'none',
          }"
        >
          <!-- 旋转的霓虹渐变背景层，通过 mask 将中间内容区域抠空 -->
          <div class="gradient-aura-container">
            <div class="gradient-aura"></div>
          </div>
          
          <!-- 磨砂玻璃感的边框描边线 -->
          <div class="glass-border-v2"></div>
        </div>

        <slot name="default" />
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
/* 容器基本样式，提供外层发光 */
.highlight-glow-box-v2 {
  position: absolute;
  background: transparent;
  box-shadow: 
    0 0 0 1px rgba(255, 255, 255, 0.05),
    0 4px 16px var(--glow-spread) rgba(31, 38, 135, 0.15);
}

/* 旋转渐变容器：定位并裁切中间 */
.gradient-aura-container {
  position: absolute;
  inset: var(--glow-inset); /* 向外溢出以展示发光范围 */
  border-radius: inherit;
  overflow: hidden;
  z-index: -1;
  filter: var(--glow-blur-filter);
  padding: var(--glow-padding); /* padding 匹配 inset 大小，从而定义 content-box 的范围 */
  
  /* 抠空中间：content-box（高亮框内部）设为透明，仅显示 border/padding 区域 */
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  -webkit-mask-composite: xor;
}

@property --angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}

/* 旋转彩虹霓虹光效：使用锥形渐变自适应任意宽高比 */
.gradient-aura {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: conic-gradient(
    from var(--angle) at 50% 50%,
    hsl(226, 81%, 64%),
    hsl(271, 81%, 64%),
    hsl(316, 81%, 64%),
    hsl(1, 81%, 64%),
    hsl(46, 81%, 64%),
    hsl(91, 81%, 64%),
    hsl(136, 81%, 64%),
    hsl(181, 81%, 64%),
    hsl(226, 81%, 64%)
  );
  animation: rotate-rainbow 4s linear infinite;
}

/* 磨砂玻璃边框线 */
.glass-border-v2 {
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  background: transparent;
  pointer-events: none;
}

@keyframes rotate-rainbow {
  to {
    --angle: 360deg;
  }
}

</style>
