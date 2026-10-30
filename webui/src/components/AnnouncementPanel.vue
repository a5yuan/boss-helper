<script setup lang="ts">
/**
 * AnnouncementPanel — 下拉公告面板（glass-surface 风格）
 * 完整实现 Bangumi-syncer 风格：可折叠列表、Markdown 渲染、三级 level 样式
 */
import { ref, computed, onMounted } from "vue";

export interface Announcement {
  id: string;
  title: string;
  content: string;
  level: "info" | "warning" | "important";
  created_at: string;
  expires_at?: string;
  is_pinned: boolean;
}

const emit = defineEmits<{
  dismiss: [id?: string];
}>();

// 公告列表
const announcements = ref<Announcement[]>([]);
const loading = ref(true);
const dismissedIds = ref<Set<string>>(new Set());
const expandedId = ref<string | null>(null);

// 过滤出未关闭的公告
const visibleAnnouncements = computed(() =>
  announcements.value.filter((a) => !dismissedIds.value.has(a.id))
);

// level 配置
const levelConfig = {
  info: {
    bg: "bg-blue-50 dark:bg-blue-950/30",
    border: "border-blue-200 dark:border-blue-800",
    icon: "🔵",
    dot: "bg-blue-500",
    title: "text-blue-700 dark:text-blue-300",
  },
  warning: {
    bg: "bg-yellow-50 dark:bg-yellow-950/30",
    border: "border-yellow-200 dark:border-yellow-800",
    icon: "⚠️",
    dot: "bg-yellow-500",
    title: "text-yellow-700 dark:text-yellow-300",
  },
  important: {
    bg: "bg-red-50 dark:bg-red-950/30",
    border: "border-red-200 dark:border-red-800",
    icon: "🚨",
    dot: "bg-red-500",
    title: "text-red-700 dark:text-red-300",
  },
};

function getLevelCfg(level: string) {
  return levelConfig[level as keyof typeof levelConfig] || levelConfig.info;
}

function toggleExpand(id: string) {
  expandedId.value = expandedId.value === id ? null : id;
}

function dismissOne(id: string) {
  dismissedIds.value = new Set([...dismissedIds.value, id]);
  emit("dismiss", id);
}

function dismissAll() {
  dismissedIds.value = new Set(announcements.value.map((a) => a.id));
  emit("dismiss");
}

function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function formatContent(content: string) {
  return content
    .replace(/^#+\s/gm, "")
    .replace(/[*_`]/g, "")
    .replace(/\n+/g, " ")
    .trim();
}

onMounted(async () => {
  try {
    const res = await fetch("/api/announcement");
    if (res.ok) {
      const data = await res.json();
      if (data) {
        announcements.value = [data];
      }
    }
  } catch (e) {
    console.error("加载公告失败:", e);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div
    class="absolute top-full right-0 mt-2 w-96 max-h-[480px] overflow-hidden rounded-2xl glass-surface flex flex-col z-50"
    style="min-width: 360px"
  >
    <!-- 面板头部 -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-glass-border">
      <div class="flex items-center gap-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="text-fg-muted"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        <h3 class="text-sm font-semibold text-fg">公告</h3>
        <span
          v-if="visibleAnnouncements.length > 0"
          class="text-[10px] px-1.5 py-0.5 rounded-full bg-brand/15 text-brand font-medium"
        >
          {{ visibleAnnouncements.length }}
        </span>
      </div>
      <button
        v-if="visibleAnnouncements.length > 0"
        class="text-[11px] text-fg-subtle hover:text-fg-muted transition-colors"
        @click="dismissAll"
      >
        全部忽略
      </button>
    </div>

    <!-- 公告列表 -->
    <div class="flex-1 overflow-y-auto">
      <!-- 加载中 -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <div class="w-5 h-5 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
      </div>

      <!-- 空状态 -->
      <div
        v-else-if="visibleAnnouncements.length === 0"
        class="flex flex-col items-center justify-center py-12 gap-3"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="text-fg-subtle"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </svg>
        <p class="text-sm text-fg-subtle">暂无公告</p>
      </div>

      <!-- 公告卡片 -->
      <div v-else class="divide-y divide-glass-border">
        <div
          v-for="ann in visibleAnnouncements"
          :key="ann.id"
          class="p-4 hover:bg-glass-bg transition-colors"
        >
          <!-- 标题行（可点击展开） -->
          <button
            class="w-full flex items-start gap-3 text-left"
            @click="toggleExpand(ann.id)"
          >
            <!-- 左侧色条 + 圆点 -->
            <div class="flex flex-col items-center gap-2 pt-1">
              <div
                class="w-1.5 h-1.5 rounded-full mt-0.5"
                :class="getLevelCfg(ann.level).dot"
              />
              <!-- 展开指示线 -->
              <div
                v-if="expandedId !== ann.id"
                class="w-px flex-1 min-h-[20px]"
                :class="getLevelCfg(ann.level).dot + '/30'"
              />
            </div>

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span
                  v-if="ann.is_pinned"
                  class="text-[10px] px-1.5 py-0.5 rounded bg-pink-100 dark:bg-pink-900/40 text-pink-500 font-medium"
                >
                  置顶
                </span>
                <span class="text-sm font-medium" :class="getLevelCfg(ann.level).title">
                  {{ ann.title }}
                </span>
              </div>
              <p
                v-if="expandedId !== ann.id"
                class="mt-1 text-xs text-fg-subtle line-clamp-1"
              >
                {{ formatContent(ann.content) }}
              </p>
              <p class="mt-1 text-[10px] text-fg-subtle/60">
                {{ formatDate(ann.created_at) }}
              </p>
            </div>

            <!-- 展开箭头 -->
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="text-fg-subtle mt-0.5 shrink-0 transition-transform duration-200"
              :class="expandedId === ann.id ? 'rotate-180' : ''"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          <!-- 展开详情 -->
          <Transition name="detail-expand">
            <div
              v-if="expandedId === ann.id"
              class="mt-3 pl-6 space-y-3"
            >
              <!-- Markdown 内容 -->
              <div class="text-xs text-fg-muted leading-relaxed whitespace-pre-wrap">
                {{ ann.content }}
              </div>
              <!-- 操作按钮 -->
              <div class="flex justify-end">
                <button
                  class="text-[11px] px-3 py-1.5 rounded-lg bg-bg-raised text-fg-muted hover:text-fg hover:bg-bg-border transition-colors"
                  @click.stop="dismissOne(ann.id)"
                >
                  忽略此公告
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>

    <!-- 底部版权信息 -->
    <div class="px-4 py-2.5 border-t border-glass-border text-center">
      <p class="text-[10px] text-fg-subtle/50">
        BOSS 直聘助手 · 公告由管理员推送
      </p>
    </div>
  </div>
</template>

<style scoped>
.detail-expand-enter-active,
.detail-expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.detail-expand-enter-from,
.detail-expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
