<!-- GlassDialog — 毛玻璃弹窗 -->
<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue?: boolean;
    title?: string;
    icon?: string;
    accent?: string;
    width?: string;
  }>(),
  {
    modelValue: false,
    title: "",
    icon: "",
    accent: "",
    width: "28rem",
  }
);

defineEmits<{
  (e: "update:modelValue", v: boolean): void;
}>();
</script>

<template>
  <Teleport to="body">
    <Transition name="gdialog">
      <div
        v-if="modelValue"
        class="gdialog-backdrop"
        @click.self="$emit('update:modelValue', false)"
      >
        <div
          class="gdialog-box"
          :style="{ maxWidth: width }"
          role="dialog"
          aria-modal="true"
        >
          <header v-if="title || icon || $slots.header" class="gdialog__header">
            <slot name="header">
              <span v-if="icon" class="gdialog__icon">{{ icon }}</span>
              <h2 class="gdialog__title" :class="accent">{{ title }}</h2>
            </slot>
          </header>

          <div class="gdialog__body">
            <slot />
          </div>

          <footer v-if="$slots.footer" class="gdialog__footer">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.gdialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.gdialog-box {
  width: 100%;
  border-radius: var(--radius-lg);
  background: var(--bg-panel);
  border: 1px solid var(--bg-border);
  box-shadow: 0 24px 64px -16px rgba(0, 0, 0, 0.32), 0 1px 0 rgba(255, 255, 255, 0.08) inset;
  overflow: hidden;
}

:root.dark .gdialog-box {
  box-shadow: 0 24px 64px -16px rgba(0, 0, 0, 0.55), 0 1px 0 rgba(255, 255, 255, 0.06) inset;
}

.gdialog__header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1.25rem 1.5rem 0;
}

.gdialog__icon {
  font-size: 1.4rem;
  line-height: 1;
  flex-shrink: 0;
}

.gdialog__title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--fg);
  line-height: 1.3;
}

.gdialog__body {
  padding: 0.875rem 1.5rem 1.25rem;
  color: var(--fg-muted);
  font-size: 0.875rem;
  line-height: 1.6;
  white-space: pre-wrap;
}

.gdialog__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.6rem;
  padding: 0 1.5rem 1.25rem;
}

/* Transition */
.gdialog-enter-active,
.gdialog-leave-active {
  transition: opacity 0.22s ease;
}
.gdialog-enter-active .gdialog-box,
.gdialog-leave-active .gdialog-box {
  transition: transform 0.22s cubic-bezier(0.34, 1.4, 0.64, 1), opacity 0.22s ease;
}
.gdialog-enter-from,
.gdialog-leave-to {
  opacity: 0;
}
.gdialog-enter-from .gdialog-box {
  transform: scale(0.93) translateY(8px);
  opacity: 0;
}
.gdialog-leave-to .gdialog-box {
  transform: scale(0.96) translateY(4px);
  opacity: 0;
}
</style>
