<!-- GlassButton — 毛玻璃按钮（glass/solid/ghost/danger 四风格 + sm/md/lg） -->
<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: "sm" | "md" | "lg";
    variant?: "glass" | "solid" | "ghost" | "danger";
    loading?: boolean;
    disabled?: boolean;
  }>(),
  { size: "md", variant: "glass", loading: false, disabled: false }
);
</script>

<template>
  <button
    class="gbtn"
    :class="[`is-${size}`, `is-${variant}`]"
    :disabled="disabled || loading"
  >
    <span class="gbtn__sheen" aria-hidden="true" />
    <span v-if="loading" class="gbtn__spinner" aria-hidden="true" />
    <span class="gbtn__label"><slot /></span>
  </button>
</template>

<style scoped>
.gbtn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-pill);
  color: var(--fg);
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  isolation: isolate;
  overflow: hidden;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  box-shadow: var(--glass-shadow), inset 0 1px 0 var(--glass-highlight);
  transition: transform var(--dur) var(--ease), background var(--dur) var(--ease),
    border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.gbtn__sheen {
  position: absolute;
  inset: 0 0 auto 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--glass-highlight), transparent);
}
.gbtn:hover {
  background: var(--glass-bg-hover);
  border-color: var(--glass-border-hover);
}
.gbtn:active {
  transform: scale(0.97);
  background: var(--glass-bg-active);
}
.gbtn:focus-visible {
  outline: none;
  box-shadow: var(--glass-shadow), inset 0 1px 0 var(--glass-highlight),
    0 0 0 3px rgba(255, 255, 255, 0.18);
}
.gbtn:disabled {
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

.is-solid {
  background: var(--btn-solid-bg);
  color: var(--btn-solid-fg);
  border-color: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: 0 8px 24px -8px rgba(17, 17, 19, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.5);
}
.is-solid:hover {
  background: var(--btn-solid-bg-hover);
  color: var(--btn-solid-fg-hover);
  transform: translateY(-1px);
}
.is-ghost {
  background: transparent;
  border-color: transparent;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  color: var(--fg-muted);
}
.is-ghost:hover {
  background: var(--glass-bg);
  color: var(--fg);
}
.is-danger {
  color: var(--danger);
  border-color: rgba(255, 90, 95, 0.3);
}
.is-danger:hover {
  background: rgba(255, 90, 95, 0.12);
  border-color: rgba(255, 90, 95, 0.5);
}

.gbtn__spinner {
  width: 0.9em;
  height: 0.9em;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.25);
  border-top-color: currentColor;
  animation: gbtn-spin 0.7s linear infinite;
}
@keyframes gbtn-spin {
  to {
    transform: rotate(360deg);
  }
}
.gbtn__label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
