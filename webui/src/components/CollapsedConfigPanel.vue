<script setup lang="ts">
/**
 * 折叠态下的 ConfigPanel 替代品：
 * - 64px 宽的 icon 抽屉（参考常见的侧边栏折叠风格）
 * - 中心一个展开按钮 + 配置 icon
 * - 不渲染任何配置项，DOM 极轻
 */
defineEmits<{
  (e: "expand"): void;
}>();
</script>

<template>
  <aside
    class="w-full h-full flex items-center justify-center"
    aria-label="配置面板已折叠"
  >
    <nav
      class="rounded-2xl bg-bg-panel/90 border border-bg-border p-1.5 flex flex-col gap-1 backdrop-blur-xl"
    >
      <button
        type="button"
        class="group relative w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200 text-fg-muted hover:text-fg hover:bg-bg-raised"
        aria-label="展开配置面板"
        @click="$emit('expand')"
      >
        <!-- 齿轮：表示"配置" -->
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
          :class="['transition-opacity duration-200 group-hover:opacity-0']"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
        <!-- 内嵌提示：hover 时 icon 淡出、文字淡入，永远不越出按钮边界 -->
        <span
          class="pointer-events-none absolute inset-0 flex items-center justify-center text-[11px] font-medium text-fg opacity-0 group-hover:opacity-100 transition-opacity duration-200"
        >
          展开
        </span>
      </button>
    </nav>
  </aside>
</template>