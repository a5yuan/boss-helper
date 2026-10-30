<script setup lang="ts">
/**
 * NotificationBell — 顶栏铃铛图标
 * 点击后展开 AnnouncementPanel 下拉面板
 * 集成未读计数 badge（参考 Bangumi-syncer 交互）
 */
import { ref, computed } from "vue";
import AnnouncementPanel from "./AnnouncementPanel.vue";

const props = defineProps<{
  /** 未读公告数量，大于 0 时显示 badge */
  unreadCount?: number;
}>();

const emit = defineEmits<{
  /** 公告被关闭时触发（单条或全部） */
  (e: "dismiss", id?: string): void;
}>();

const isOpen = ref(false);
const panelRef = ref<HTMLElement | null>(null);

// 超过 99 显示 99+
const badgeText = computed(() => {
  const n = props.unreadCount ?? 0;
  return n > 99 ? "99+" : String(n);
});

function toggle() {
  isOpen.value = !isOpen.value;
}

function handleDismiss(id?: string) {
  emit("dismiss", id);
  // 关闭时如果是单条关闭，保持面板打开
}

function handleClickOutside(e: MouseEvent) {
  if (isOpen.value && panelRef.value && !panelRef.value.contains(e.target as Node)) {
    isOpen.value = false;
  }
}

// 挂载后监听外部点击
import { onMounted, onUnmounted } from "vue";
onMounted(() => document.addEventListener("click", handleClickOutside, true));
onUnmounted(() => document.removeEventListener("click", handleClickOutside, true));
</script>

<template>
  <div ref="panelRef" class="relative">
    <!-- 铃铛按钮 -->
    <button
      class="relative w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200"
      :class="
        isOpen
          ? 'bg-brand/15 text-brand'
          : 'text-fg-muted hover:text-fg hover:bg-bg-raised'
      "
      :title="isOpen ? '收起公告' : '查看公告'"
      @click.stop="toggle"
    >
      <!-- SVG Bell -->
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>

      <!-- 未读 badge -->
      <span
        v-if="unreadCount && unreadCount > 0"
        class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-danger text-[10px] font-bold text-white flex items-center justify-center leading-none shadow-sm"
      >
        {{ badgeText }}
      </span>
    </button>

    <!-- 下拉面板 -->
    <Transition name="panel-drop">
      <AnnouncementPanel
        v-if="isOpen"
        @dismiss="handleDismiss"
      />
    </Transition>
  </div>
</template>

<style scoped>
.panel-drop-enter-active,
.panel-drop-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.panel-drop-enter-from,
.panel-drop-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}
</style>
