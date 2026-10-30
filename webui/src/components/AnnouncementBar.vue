<script setup lang="ts">
import { ref, computed } from "vue";

export interface Announcement {
  id: string;
  title: string;
  content: string;
  level: "info" | "warning" | "important";
  created_at: string;
  expires_at?: string;
  is_pinned: boolean;
}

const props = defineProps<{
  announcement: Announcement;
}>();

const emit = defineEmits<{
  dismiss: [];
}>();

const expanded = ref(false);

// 根据 level 确定样式
const levelConfig = computed(() => {
  const configs = {
    info: {
      bg: "bg-blue-100 dark:bg-blue-900/40",
      border: "border-blue-500",
      icon: "🔵",
      text: "text-blue-700 dark:text-blue-300",
    },
    warning: {
      bg: "bg-yellow-100 dark:bg-yellow-900/40",
      border: "border-yellow-500",
      icon: "⚠️",
      text: "text-yellow-700 dark:text-yellow-300",
    },
    important: {
      bg: "bg-red-100 dark:bg-red-900/40",
      border: "border-red-500",
      icon: "🚨",
      text: "text-red-700 dark:text-red-300",
    },
  };
  return configs[props.announcement.level] || configs.info;
});

// 格式化时间
function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}
</script>

<template>
  <div
    class="announcement-bar flex items-start gap-3 px-4 py-3 border-l-4 transition-all duration-300"
    :class="[levelConfig.bg, levelConfig.border]"
  >
    <!-- 图标 -->
    <span class="text-lg mt-0.5 shrink-0">{{ levelConfig.icon }}</span>

    <!-- 内容区 -->
    <div class="flex-1 min-w-0">
      <!-- 标题行 -->
      <button
        class="w-full flex items-center justify-between gap-2 text-left"
        @click="expanded = !expanded"
      >
        <div class="flex items-center gap-2">
          <h3
            class="font-medium text-sm"
            :class="levelConfig.text"
          >
            {{ announcement.title }}
          </h3>
          <span
            v-if="announcement.is_pinned"
            class="text-[10px] px-1.5 py-0.5 rounded bg-pink-100 dark:bg-pink-900/40 text-pink-600 dark:text-pink-300"
          >
            置顶
          </span>
        </div>
        <span
          class="text-fg-subtle transition-transform duration-200"
          :class="expanded ? 'rotate-180' : ''"
        >
          ▼
        </span>
      </button>

      <!-- 摘要（收起时） -->
      <p
        v-if="!expanded"
        class="mt-1 text-xs text-fg-subtle line-clamp-1"
      >
        {{ announcement.content.replace(/[#*`]/g, "").slice(0, 100) }}...
      </p>

      <!-- 展开详情 -->
      <div
        v-if="expanded"
        class="mt-2 text-xs text-fg-muted space-y-2"
      >
        <!-- 格式化的时间 -->
        <p class="text-[10px] opacity-60">
          发布时间: {{ formatDate(announcement.created_at) }}
        </p>
        <!-- 内容（Markdown 简化渲染） -->
        <div class="prose prose-sm dark:prose-invert max-w-none">
          <template v-for="(line, i) in announcement.content.split('\n')" :key="i">
            <p v-if="line.trim()" class="my-1">{{ line }}</p>
          </template>
        </div>
      </div>
    </div>

    <!-- 关闭按钮 -->
    <button
      class="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-fg-subtle hover:text-fg hover:bg-bg-raised transition-colors"
      title="关闭公告"
      @click="emit('dismiss')"
    >
      ✕
    </button>
  </div>
</template>

<style scoped>
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
