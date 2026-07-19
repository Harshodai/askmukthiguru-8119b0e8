import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { visualizer } from "rollup-plugin-visualizer";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_BACKEND_URL || "http://localhost:8000";
  const isProd = mode === "production";
  return {
    server: {
      host: "::",
      port: 8080,
      hmr: { overlay: false },
      watch: {
        ignored: ["**/.docker_clean/**"],
      },
      proxy: {
        "/api": {
          target: backend,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    plugins: [
      react(),
      isProd && visualizer({
        filename: "dist/stats.html",
        open: false,
        gzipSize: true,
        brotliSize: true,
      }),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
      dedupe: ["react", "react-dom"],
    },
    build: {
      chunkSizeWarningLimit: 500,
      cssCodeSplit: true,
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            if (id.includes('node_modules')) {
              if (id.includes('react') || id.includes('react-dom') || id.includes('react-router-dom')) {
                return 'react-vendor';
              }
              if (id.includes('framer-motion') || id.includes('lucide-react')) {
                return 'ui-vendor';
              }
              if (id.includes('recharts') || id.includes('victory-vendor') || id.includes('d3-')) {
                // No manualChunks assignment: these ship only via the admin
                // sub-app's lazy routes (see src/App.tsx ADMIN_ENABLED block).
                // Force-naming them 'chart-vendor' merged them with a copy of
                // React's runtime in rolldown's output, which made the whole
                // chunk eagerly modulepreloaded from index.html. Returning
                // undefined lets rolldown's default async-chunk splitting
                // place them in a chunk that's only fetched when an admin
                // route actually imports them.
                return undefined;
              }
              if (id.includes('@supabase/supabase-js')) {
                return 'supabase-vendor';
              }
              if (id.includes('react-markdown') || id.includes('remark-gfm')) {
                return 'markdown-vendor';
              }
              if (id.includes('date-fns') || id.includes('lodash-es') || id.includes('clsx') || id.includes('tailwind-merge')) {
                return 'utils-vendor';
              }
              return 'vendor';
            }
          },
          chunkFileNames: 'assets/js/[name]-[hash].js',
          entryFileNames: 'assets/js/[name]-[hash].js',
          assetFileNames: (assetInfo) => {
            const name = assetInfo.name ?? '';
            const info = name.split('.');
            const ext = info[info.length - 1];
            if (/\.(png|jpe?g|gif|svg|webp|avif|ico)$/.test(name)) {
              return `assets/images/[name]-[hash].${ext}`;
            }
            if (/\.(woff2?|ttf|eot)$/.test(name)) {
              return `assets/fonts/[name]-[hash].${ext}`;
            }
            if (/\.css$/.test(name)) {
              return `assets/css/[name]-[hash].${ext}`;
            }
            return `assets/[name]-[hash].${ext}`;
          },
        },
      },
      minify: 'esbuild',
      target: 'es2020',
      reportCompressedSize: true,
    },
    esbuild: {
      treeShaking: true,
      pure: isProd ? ['console.log', 'console.debug'] : [],
    },
  };
});

