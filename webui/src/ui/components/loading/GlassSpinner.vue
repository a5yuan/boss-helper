<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    size?: number;
    duration?: number;
  }>(),
  {
    size: 48,
    duration: 1.7,
  }
);
</script>

<template>
  <div
    class="glass-spinner"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      animationDuration: `${duration}s`,
    }"
  />
</template>

<style>
/* ============================================================
 * GlassSpinner — 方形、保留 Uiverse 那套紫/青渐变发光光效
 * ============================================================ */
.glass-spinner {
  --purple: 186, 66, 255;
  --cyan: 0, 225, 255;

  position: relative;
  border-radius: 14px;
  background: linear-gradient(
    rgb(var(--purple)) 0%,
    rgb(var(--cyan)) 100%
  );
  filter: blur(1px);
  box-shadow:
    0px -6px 20px 0px rgb(var(--purple)),
    0px 6px 20px 0px rgb(var(--cyan));
  animation: glass-spin var(--dur, 1.7s) linear infinite;
}

.glass-spinner::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: rgba(24, 24, 27, 0.72);
  filter: blur(8px);
}

@keyframes glass-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
