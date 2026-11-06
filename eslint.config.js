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
      ".tmp_release_evidence",
      ".tmp_release_evidence/**",
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
      ".claude/worktrees",
      ".claude/worktrees/**",
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
      // T1-16: API calls must use the backend URL helper (src/lib/backendUrl.ts);
      // a relative "/api/..." fetch breaks on static hosts and native builds.
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch'] > Literal[value=/^.api./]",
          message: "Use `${BACKEND_URL}/api/...` from '@/lib/backendUrl' instead of a relative /api fetch.",
        },
        {
          selector: "CallExpression[callee.name='fetch'] > TemplateLiteral > TemplateElement:first-child[value.raw=/^.api./]",
          message: "Use `${BACKEND_URL}/api/...` from '@/lib/backendUrl' instead of a relative /api fetch.",
        },
        // NEW-LOV-03: generated (Lovable) code reaches the API through other call forms too.
        {
          selector: "NewExpression[callee.name='EventSource'] > Literal[value=/^.api./]",
          message: "Use `${BACKEND_URL}/api/...` from '@/lib/backendUrl' instead of a relative /api EventSource.",
        },
        {
          selector: "NewExpression[callee.name='EventSource'] > TemplateLiteral > TemplateElement:first-child[value.raw=/^.api./]",
          message: "Use `${BACKEND_URL}/api/...` from '@/lib/backendUrl' instead of a relative /api EventSource.",
        },
        {
          selector: "CallExpression[callee.property.name='sendBeacon'] > Literal:first-child[value=/^.api./]",
          message: "Use `${BACKEND_URL}/api/...` from '@/lib/backendUrl' instead of a relative /api beacon.",
        },
      ],
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
