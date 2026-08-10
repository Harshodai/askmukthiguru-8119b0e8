# ============================================================
# AskMukthiGuru — Frontend Dockerfile
# Multi-stage: build React app with Vite, serve with Nginx
# ============================================================

# --- Stage 1: Build the React app ---
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm install --legacy-peer-deps

# Build arguments for environment variables
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ARG VITE_USE_NATIVE_OAUTH
ARG VITE_JAEGER_UI_URL
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_BACKEND_URL

# Set them as environment variables for the build process
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY
ENV VITE_USE_NATIVE_OAUTH=$VITE_USE_NATIVE_OAUTH
ENV VITE_JAEGER_UI_URL=$VITE_JAEGER_UI_URL
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL

# Copy source code and build
COPY index.html vite.config.ts tsconfig*.json tailwind.config.ts postcss.config.js components.json ./
COPY src/ ./src/
COPY public/ ./public/
COPY scripts/ ./scripts/

# Build for production
RUN NODE_OPTIONS="--max-old-space-size=4096" npm run build

# --- Stage 2: Serve with Nginx ---
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy the built React app
COPY --from=builder /app/dist /usr/share/nginx/html/app

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/health || exit 1

# Drop privileges: nginx master would otherwise run as root (container
# escape = root on host). Make its writable paths (cache, pid, logs) owned
# by the image's `nginx` system user (uid 101) before switching users.
# nginx.conf (conf.d/default.conf) sets no pid/temp directives, so the image
# defaults apply: pid /run/nginx.pid (via /var/run -> ../run symlink), logs
# under /var/log/nginx, and client_body/proxy temp dirs under /var/cache/nginx
# (proxying /api with buffering on writes proxy temp files). Note: busybox
# chown lchowns a symlink operand, so chown the real /run target, not
# /var/run, or the pid dir stays root-owned and nginx exits with
# 'open() "/run/nginx.pid" failed (13: Permission denied)'.
RUN chown -R nginx:nginx /var/cache/nginx /run /var/log/nginx

USER nginx

CMD ["nginx", "-g", "daemon off;"]
