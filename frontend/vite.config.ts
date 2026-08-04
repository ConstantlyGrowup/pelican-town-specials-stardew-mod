import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // e2e specs run under Playwright, not vitest.
    exclude: ["e2e/**", "node_modules/**", "dist/**", "test-results/**", "playwright-report/**"],
  },
});
