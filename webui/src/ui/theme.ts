import { ref } from "vue";

export type ThemeMode = "light" | "dark";

const STORAGE_KEY = "boss-theme";
const mode = ref<ThemeMode>("light");

function apply(m: ThemeMode) {
  document.documentElement.classList.toggle("dark", m === "dark");
}

/** 在应用入口调用一次：读取本地存储并应用（默认 light） */
export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
  mode.value = saved === "dark" ? "dark" : "light";
  apply(mode.value);
}

export function useTheme() {
  function setMode(m: ThemeMode) {
    mode.value = m;
    localStorage.setItem(STORAGE_KEY, m);
    apply(m);
  }
  function toggle() {
    setMode(mode.value === "light" ? "dark" : "light");
  }
  return { mode, setMode, toggle };
}
