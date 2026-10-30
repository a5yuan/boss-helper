import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  const backendUrl =
    env.VITE_BACKEND_URL || "http://127.0.0.1:8848";
  const serverPort = parseInt(env.VITE_PORT || "5173", 10);

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      host: "127.0.0.1",
      port: serverPort,
      proxy: {
        "/api": { target: backendUrl, changeOrigin: true },
        "/ws": { target: backendUrl.replace("http", "ws"), ws: true },
        "/__debug_log": { target: backendUrl, changeOrigin: true },
        "/__debug_panel": { target: backendUrl, changeOrigin: true },
      },
    },
    build: {
      outDir: "../server/static",
      emptyOutDir: true,
    },
  };
});
