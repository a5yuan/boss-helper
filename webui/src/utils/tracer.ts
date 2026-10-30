/**
 * Boss 助手前端调试追踪器
 *
 * 直接导出标准 tracelink tracer 单例。
 * 开发环境自动连接 Dashboard Receiver + 自动点击追踪。
 */
import { tracer } from "tracelink";
import { BrowserHttpExporter } from "tracelink/browser";

// 开发环境：连接 Dashboard Receiver
if (import.meta.env.DEV) {
  const receiverEndpoint = "http://127.0.0.1:5174/__debug_log";
  const exporter = new BrowserHttpExporter({
    endpoint: receiverEndpoint,
    getEnabledScopes: () => tracer.getEnabledScopes(),
  });
  tracer.configure({
    enabled: true,
    httpExporter: (log) => exporter.send(log),
    scopeSync: { endpoint: `${receiverEndpoint}/scopes` },
  });

  // 自动点击追踪
  import("tracelink/browser")
    .then(({ installAutoClick }) => installAutoClick())
    .catch(() => {});

  console.log(
    "%c[TraceLink] 就绪 — window.__trace 可用",
    "color:#4CAF50;font-weight:bold"
  );
}

// 控制台调试入口
if (typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).__trace = tracer;
}

export { tracer };
