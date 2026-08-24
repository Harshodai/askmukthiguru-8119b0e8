import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import fs from "fs";
import path from "path";
import { visualizer } from "rollup-plugin-visualizer";

const STATIC_ASSET_RE = /^\/assets\/.+\.(?:js|css|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|eot|json|webmanifest)$/i;

// Keep missing hashed assets from falling through to the SPA shell during local preview.
// A 200 HTML response for a missing script is a silent, hard-to-diagnose production failure.
const strictStaticAssetPreview = {
  name: "strict-static-asset-preview",
  configurePreviewServer(server: { middlewares: { use: (handler: (req: { url?: string }, res: { statusCode: number; setHeader: (name: string, value: string) => void; end: (body: string) => void }, next: () => void) => void) => void } }) {
    server.middlewares.use((req, res, next) => {
      const pathname = (req.url ?? "").split("?", 1)[0];
      if (!STATIC_ASSET_RE.test(pathname)) {
        next();
        return;
      }

      const assetPath = path.resolve(process.cwd(), "dist", `.${pathname}`);
      const distRoot = path.resolve(process.cwd(), "dist") + path.sep;
      if (!assetPath.startsWith(distRoot) || !fs.existsSync(assetPath)) {
        res.statusCode = 404;
        res.setHeader("Content-Type", "text/plain; charset=utf-8");
        res.end("Not Found");
        return;
      }
      next();
    });
  },
};

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const fileEnv = loadEnv(mode, process.cwd(), "");
  // Hosted builders (Lovable, Railway, CI) inject config through process.env and
  // never ship a .env file — merge both so the guard below only fires when the
  // values are genuinely absent everywhere.
  const env = { ...fileEnv, ...(process.env as Record<string, string>) };
  const backend = env.VITE_BACKEND_URL || "http://localhost:8000";
  const isProd = mode === "production";
  if (
    command === "build" &&
    isProd &&
    (!env.VITE_SUPABASE_URL || !env.VITE_SUPABASE_PUBLISHABLE_KEY)
  ) {
    throw new Error(
      "VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY must be set for a production build. " +
        "Add them to .env (or .env.production) — the frontend no longer falls back to the production Supabase project.",
    );
  }
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
      strictStaticAssetPreview,
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
      // The measured shared entry is 536 kB; retain a modest 600 kB budget for production warnings.
      chunkSizeWarningLimit: 600,
      cssCodeSplit: true,
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            if (id.includes('node_modules')) {
              // Match on the package directory boundary, not a bare substring:
              // `id.includes('react')` also caught every @radix-ui/react-*,
              // react-i18next, react-markdown, react-hook-form… and dragged
              // them all into the eagerly-preloaded react-vendor chunk
              // (782 kB / 251 kB gzip on the critical path).
              if (/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//.test(id)) {
                return 'react-vendor';
              }
              if (id.includes('framer-motion') || id.includes('lucide-react')) {
                return 'ui-vendor';
              }
              if (id.includes('@radix-ui') || id.includes('@floating-ui')) {
                return 'radix-vendor';
              }
              if (id.includes('i18next') || id.includes('react-i18next')) {
                return 'i18n-vendor';
              }
              if (id.includes('@tanstack/react-query')) {
                return 'query-vendor';
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
              // react-markdown / remark-gfm are imported by ChatMessage only.
              // Force-naming them made rolldown modulepreload the chunk from
              // index.html (124 kB eager for a route most visitors never open);
              // unnamed, they ride along in the lazy ChatPage chunk.
              if (id.includes('date-fns') || id.includes('lodash-es') || id.includes('clsx') || id.includes('tailwind-merge')) {
                return 'utils-vendor';
              }
              // No catch-all 'vendor' chunk: forcing every remaining dependency
              // into one chunk meant a single eager import (Radix, i18next…)
              // dragged ~700 kB onto the critical path. Same rationale as the
              // chart-vendor note above — let rolldown's async-chunk splitting
              // keep route-only dependencies off the initial load.
              return undefined;
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
      minify: isProd,
      target: 'es2020',
      reportCompressedSize: true,
    },
  };
});

