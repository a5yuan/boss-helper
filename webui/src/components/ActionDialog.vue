<script setup lang="ts">
import { computed } from "vue";
import { useEngine } from "@/stores/engine";
import { GlassDialog } from "@/ui";
import GlassButton from "@/ui/components/button/GlassButton.vue";

const engine = useEngine();

const open = computed({
  get: () => !!engine.pendingAction,
  set: () => engine.ack(""),
});

const meta = computed(() => {
  const kind = engine.pendingAction?.kind || "confirm";
  return (
    {
      captcha: { icon: "🛡️", title: "需要完成验证码", accent: "text-amber-400" },
      login: { icon: "🔑", title: "登录可能已失效", accent: "text-rose-400" },
      page_check: { icon: "🧭", title: "请确认页面状态", accent: "" },
      page_confirm: { icon: "🧭", title: "请确认页面状态", accent: "" },
      confirm: { icon: "❓", title: "需要确认", accent: "" },
    } as Record<string, { icon: string; title: string; accent: string }>
  )[kind];
});

const isPageCheck = computed(() => engine.pendingAction?.kind === "page_check");
const isPageConfirm = computed(() => engine.pendingAction?.kind === "page_confirm");
</script>

<template>
  <GlassDialog
    v-model="open"
    :icon="meta.icon"
    :title="meta.title"
    :accent="meta.accent"
    width="26rem"
  >
    <p class="text-sm text-fg-muted whitespace-pre-wrap leading-relaxed">
      {{ engine.pendingAction?.reason }}
    </p>
    <p class="mt-3 text-xs text-fg-subtle">
      请切换到浏览器窗口完成操作，处理好后点击下方按钮继续。
    </p>

    <template #footer>
      <div class="flex gap-2 flex-wrap">
        <GlassButton v-if="isPageCheck" variant="ghost" size="sm" @click="engine.ack('manual_scroll')">
          已手动滚动/翻页
        </GlassButton>
        <GlassButton v-if="isPageCheck || isPageConfirm" variant="ghost" size="sm" @click="engine.ack('wait')">
          我要先手动操作
        </GlassButton>
        <GlassButton variant="solid" size="sm" @click="engine.ack('')">
          我已完成，继续
        </GlassButton>
      </div>
    </template>
  </GlassDialog>
</template>
