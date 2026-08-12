import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "dist/**",
      "node_modules",
      "node_modules/**",
      ".venv",
      ".venv/**",
      ".venv_host",
      ".venv_host/**",
      "backend/.venv",
      "backend/.venv/**",
      "backend/__pycache__",
      "**/__pycache__/**",
      "playwright-report",
      "playwright-report/**",
      "test-results",
      "test-results/**",
      "external_repos",
      "external_repos/**",
      "mcp-servers",
      "mcp-servers/**",
      ".hyperresearch-venv",
      ".hyperresearch-venv/**",
      "supabase/.temp",
      "supabase/.temp/**",
      "android",
      "android/**",
      "ios",
      "ios/**",
      "public/push-sw.js",
      "*.config.js",
      "postcss.config.js",
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": "off",
      // Generated UI components legitimately use empty object types for extension patterns
      "@typescript-eslint/no-empty-object-type": "off",
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    rules: {
      // Test doubles mirror browser and SDK globals whose runtime shapes are intentionally dynamic.
      "@typescript-eslint/no-explicit-any": "off",
      "no-empty-pattern": "off",
    },
  },
);
