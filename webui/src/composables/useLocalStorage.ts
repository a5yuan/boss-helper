/**
 * useLocalStorage —— 响应式 + 自动持久化的本地存储 ref。
 *
 * 设计要点（"最优秀写法"考量）：
 * 1. SSR / 非浏览器环境安全（typeof window 守卫，不抛 ReferenceError）
 * 2. JSON 容错：解析失败时静默回退到默认值 + 清理坏值，避免下次启动再炸
 * 3. 单 storage 事件跨标签同步（多标签开同一应用时一处折叠全部折叠）
 * 4. 自定义 validator：拿到的值不合法时拒绝写入并保留旧值（防止脏数据）
 * 5. 一次只挂一个 storage listener，组件卸载自动清理（无内存泄漏）
 *
 * 用法：
 *   const collapsed = useLocalStorage('boss-config-collapsed', false)
 *   collapsed.value = true   // 自动写入 localStorage 并触发 storage 事件
 */
import { onScopeDispose, ref, watch, type Ref } from "vue";

const isBrowser = typeof window !== "undefined";

export interface UseLocalStorageOptions<T> {
  /** 自定义校验：返回 false 则拒绝写入（保留旧值） */
  validator?: (raw: unknown) => raw is T;
  /** 把值序列化成字符串（默认 JSON.stringify） */
  serializer?: (v: T) => string;
  /** 反序列化（默认 JSON.parse） */
  deserializer?: (raw: string) => T;
}

function defaultRead<T>(key: string, fallback: T): T {
  if (!isBrowser) return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    // 损坏的 JSON —— 清理一次，避免污染下次启动
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* quota / privacy mode 静默吞 */
    }
    return fallback;
  }
}

function defaultWrite(key: string, value: unknown): void {
  if (!isBrowser) return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / privacy mode 静默吞 */
  }
}

export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
  options: UseLocalStorageOptions<T> = {}
): Ref<T> {
  const { validator, serializer, deserializer } = options;

  // 读初始值
  const initial = defaultRead<T>(key, defaultValue);
  const safeInitial =
    validator && !validator(initial) ? defaultValue : initial;

  const state = ref(safeInitial) as Ref<T>;

  // 写：watch 触发，把 ref 当前值持久化
  watch(
    state,
    (v) => {
      if (validator && !validator(v)) return; // 脏值拒绝
      const serialized = serializer ? serializer(v) : JSON.stringify(v);
      if (serializer) {
        // 自定义 serializer 不走 JSON.stringify；手动写入
        try {
          window.localStorage.setItem(key, serialized);
        } catch {
          /* quota / privacy mode 静默吞 */
        }
      } else {
        defaultWrite(key, v);
      }
    },
    { deep: true }
  );

  // 跨标签同步
  if (isBrowser) {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== key || e.newValue === null) return;
      try {
        const next: T = deserializer
          ? deserializer(e.newValue)
          : (JSON.parse(e.newValue) as T);
        if (validator && !validator(next)) return;
        state.value = next;
      } catch {
        /* 其他标签写入了坏值：忽略 */
      }
    };
    window.addEventListener("storage", onStorage);
    onScopeDispose(() => window.removeEventListener("storage", onStorage));
  }

  return state;
}