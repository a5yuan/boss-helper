<script setup lang="ts">
/**
 * TaskTabs：多平台任务标签栏。
 * 只在同时存在两个及以上任务时渲染；单任务时整块 DOM 不存在，保持原界面。
 */
import { computed } from "vue";
import { useEngine, type TaskState } from "@/stores/engine";

const engine = useEngine();

const activeId = computed(() => engine.activeTaskId ?? engine.activeTask?.taskId ?? null);

// 按 taskOrder 展开成任务对象，模板里就不用反复做存在性判断
const tabs = computed<TaskState[]>(() =>
  engine.taskOrder
    .map((id) => engine.tasks[id] as TaskState | undefined)
    .filter((t): t is TaskState => !!t)
);

function dotClass(task: TaskState): string {
  return (
    {
      running: "bg-brand animate-pulse-ring",
      paused: "bg-amber-500 animate-pulse-ring",
      waiting: "bg-amber-500 animate-pulse-ring",
      done: "bg-emerald-500",
      stopped: "bg-fg-subtle",
      error: "bg-rose-500",
    } as Record<string, string>
  )[task.state] || "bg-fg-subtle";
}

function close(taskId: string) {
  engine.closeTask(taskId);
}
</script>

<template>
  <div
    v-if="engine.multiTask"
    id="task-tabs"
    class="flex items-center gap-1.5 overflow-x-auto pb-0.5"
  >
    <div
      v-for="task in tabs"
      :key="task.taskId"
      class="flex items-center shrink-0 rounded-lg border transition-colors"
      :class="task.taskId === activeId
        ? 'bg-bg-raised border-glass-border-hover'
        : 'bg-bg-base/40 border-bg-border'"
    >
      <button
        type="button"
        :data-task-tab="task.taskId"
        :data-platform="task.platform"
        class="flex items-center gap-2 pl-3 pr-2 py-1.5 text-xs transition-colors"
        :class="task.taskId === activeId ? 'text-fg font-medium' : 'text-fg-muted hover:text-fg'"
        :title="task.pendingAction?.reason || engine.platformLabel(task.platform)"
        @click="engine.selectTask(task.taskId)"
      >
        <span class="w-2 h-2 rounded-full shrink-0" :class="dotClass(task)"></span>
        <span>{{ engine.platformLabel(task.platform) }}</span>
      </button>
      <button
        v-if="!task.running"
        type="button"
        :data-tab-close="task.taskId"
        class="pr-2.5 pl-0.5 py-1.5 text-xs text-fg-subtle hover:text-fg transition-colors"
        title="关闭任务"
        aria-label="关闭任务"
        @click.stop="close(task.taskId)"
      >
        ×
      </button>
    </div>
  </div>
</template>
