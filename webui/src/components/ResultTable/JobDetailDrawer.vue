<script setup lang="ts">
import type { Job } from "@/api";

const props = defineProps<{ job: Job | null }>();
const emit = defineEmits<{ (e: "close"): void }>();

function arrayField(value: unknown): string[] {
  return Array.isArray(value) ? (value as string[]) : [];
}

function open() {
  return !!props.job;
}
</script>

<template>
  <!-- 半透明遮罩 + 右侧抽屉 -->
  <Transition name="fade">
    <div
      v-if="open()"
      class="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
      @click="emit('close')"
    ></div>
  </Transition>

  <Transition name="slide">
    <aside
      v-if="open()"
      class="fixed top-0 right-0 bottom-0 z-50 w-full max-w-[640px] bg-bg-panel border-l border-bg-border shadow-2xl overflow-y-auto"
    >
      <!-- 头部：不透明背景 + 无 backdrop-blur（避免 header 自身模糊下方内容） -->
      <header class="sticky top-0 z-10 bg-bg-panel px-6 py-4 border-b border-bg-border flex items-start gap-3">
        <div class="flex-1 min-w-0">
          <h2 class="text-lg font-semibold text-fg truncate">{{ props.job!.title }}</h2>
          <div class="mt-1 text-sm text-fg-subtle truncate">
            <span class="text-fg">{{ props.job!.company }}</span>
            <span v-if="props.job!.salary" class="ml-2 text-emerald-400">{{ props.job!.salary }}</span>
          </div>
          <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-fg-subtle">
            <span v-if="props.job!.location">{{ props.job!.location }}</span>
            <span v-if="props.job!.experience">{{ props.job!.experience }}</span>
            <span v-if="props.job!.degree">{{ props.job!.degree }}</span>
            <span v-if="props.job!.industry">{{ props.job!.industry }}</span>
          </div>
        </div>
        <button class="btn-ghost !py-1.5 text-xs" @click="emit('close')">关闭</button>
      </header>

      <!-- 标签区：7 个集合 -->
      <section class="px-6 py-4 flex flex-col gap-3 border-b border-bg-border">
        <TagBlock label="技能" :items="arrayField(props.job!.skills)" />
        <TagBlock label="福利" :items="arrayField(props.job!.welfare)" />
        <TagBlock label="岗位标签" :items="arrayField(props.job!.job_labels)" />
        <TagBlock label="公司标签" :items="arrayField(props.job!.company_labels)" />
      </section>

      <!-- JD -->
      <section class="px-6 py-4">
        <h3 class="text-xs font-semibold text-fg-subtle uppercase tracking-wide mb-2">职位描述</h3>
        <pre class="whitespace-pre-wrap break-words text-sm text-fg leading-6 font-sans">{{ props.job!.jd }}</pre>
      </section>
    </aside>
  </Transition>
</template>

<script lang="ts">
import { defineComponent, h } from "vue";
import { GlassTag } from "@/ui";

/** 小块标签：标题 + 一行 chip（不存在则整块隐藏）。 */
const TagBlock = defineComponent({
  name: "TagBlock",
  props: { label: { type: String, required: true }, items: { type: Array, required: true } },
  setup(p) {
    return () =>
      p.items.length
        ? h("div", [
            h("div", { class: "text-xs font-semibold text-fg-subtle uppercase tracking-wide mb-1.5" }, p.label),
            h(
              "div",
              { class: "flex flex-wrap gap-1.5" },
              p.items.map((it: unknown) =>
                h(
                  GlassTag,
                  { variant: "default" },
                  { default: () => String(it) }
                )
              )
            ),
          ])
        : null;
  },
});

export default { components: { TagBlock } };
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .18s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.slide-enter-active, .slide-leave-active { transition: transform .22s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>