<!-- GlassCard — 毛玻璃卡片 -->
<script setup lang="ts">
withDefaults(defineProps<{ padded?: boolean }>(), { padded: true });
</script>

<template>
  <section class="gcard glass-hairline" :class="{ 'is-pad': padded }">
    <header v-if="$slots.header" class="gcard__header"><slot name="header" /></header>
    <div class="gcard__body"><slot /></div>
  </section>
</template>

<style scoped>
.gcard {
  border-radius: var(--radius-lg);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  box-shadow: var(--glass-shadow), inset 0 1px 0 var(--glass-highlight);
  overflow: hidden;
}
.is-pad {
  padding: 1.25rem 1.5rem;
}
.gcard__header {
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 0.75rem;
}
.gcard__body {
  color: var(--fg-muted);
}
</style>
