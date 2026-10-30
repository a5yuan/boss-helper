<!-- MatteButton — 哑光金属按钮（同类不同风：厚重深色金属质感） -->
<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: "sm" | "md" | "lg";
    disabled?: boolean;
  }>(),
  { size: "md", disabled: false }
);
</script>

<template>
  <button class="mbtn" :class="`is-${size}`" :disabled="disabled">
    <span class="mbtn__label"><slot /></span>
  </button>
</template>

<style scoped>
.mbtn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-pill);
  color: rgba(255, 255, 255, 0.9);
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  background: linear-gradient(180deg, #2a2a2e, #161618);
  box-shadow: 0 6px 18px -6px rgba(0, 0, 0, 0.8),
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    inset 0 -1px 0 rgba(0, 0, 0, 0.6);
  transition: transform var(--dur) var(--ease), background var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}
.mbtn:hover {
  background: linear-gradient(180deg, #313136, #1c1c1f);
  box-shadow: 0 10px 24px -8px rgba(0, 0, 0, 0.85),
    inset 0 1px 0 rgba(255, 255, 255, 0.12),
    inset 0 -1px 0 rgba(0, 0, 0, 0.6);
}
.mbtn:active {
  transform: scale(0.97);
}
.mbtn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.is-sm {
  padding: 0.4rem 0.85rem;
  font-size: 0.78rem;
}
.is-md {
  padding: 0.55rem 1.15rem;
  font-size: 0.875rem;
}
.is-lg {
  padding: 0.7rem 1.5rem;
  font-size: 1rem;
}
</style>
