import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_BACKEND_URL || "http://localhost:8000";
  return {
    server: {
      host: "::",
      port: 8080,
      hmr: { overlay: false },
      watch: {
        ignored: ["**/.docker_clean/**"],
      },
      // Proxy /api in dev so the FastAPI backend handles chat/memory requests
      // instead of Vite returning index.html (which silently breaks streaming).
      proxy: {
        "/api": {
          target: backend,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      chunkSizeWarningLimit: 2000,
    },
  };
});

