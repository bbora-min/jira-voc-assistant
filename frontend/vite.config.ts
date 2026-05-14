import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "");
  const apiBase = env.VITE_API_BASE || "http://localhost:8080";
  const wsBase = env.VITE_WS_BASE || "ws://localhost:8080";
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": { target: apiBase, changeOrigin: true },
        "/health": { target: apiBase, changeOrigin: true },
        "/ws": { target: wsBase, ws: true, changeOrigin: true },
      },
    },
  };
});
