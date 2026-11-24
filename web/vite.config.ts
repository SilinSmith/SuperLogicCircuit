/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev 5174（避开旧工程的 5173）；/api 代理到 rvgen serve 的 8123。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8123",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5174,
    strictPort: true,
  },
  build: {
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    css: false,
  },
});
