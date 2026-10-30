<!-- GlassTag — 毛玻璃标签 -->
<script setup lang="ts">
withDefaults(
  defineProps<{ variant?: "default" | "brand" | "danger" | "success" }>(),
  { variant: "default" }
);
</script>

<template>
  <span class="gtag" :class="`is-${variant}`"><slot /></span>
</template>

<style scoped>
.gtag {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-pill);
  font-size: 0.72rem;
  font-weight: 500;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--fg-muted);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.is-brand {
  color: var(--fg);
  border-color: rgba(255, 255, 255, 0.25);
  background: rgba(255, 255, 255, 0.1);
}
.is-danger {
  color: var(--danger);
  border-color: rgba(255, 90, 95, 0.3);
  background: rgba(255, 90, 95, 0.1);
}
.is-success {
  color: var(--success);
  border-color: rgba(74, 222, 128, 0.3);
  background: rgba(74, 222, 128, 0.1);
}
</style>
