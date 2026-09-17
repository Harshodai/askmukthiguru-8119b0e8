import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text"],
      // Ratchet, not a cliff: floors set a couple points below the measured
      // baseline (2026-09-16, `npx vitest run --coverage`: statements
      // 54.57%, branches 44.5%, functions 44.8%, lines 57.14%) so normal
      // test-count drift doesn't flake CI. Raise these as coverage improves;
      // never lower them to paper over a regression. Mirrors the backend
      // floor convention in backend/pyproject.toml [tool.coverage.report].
      thresholds: {
        statements: 52,
        branches: 42,
        functions: 42,
        lines: 54,
      },
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
