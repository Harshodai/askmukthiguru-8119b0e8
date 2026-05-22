# ============================================================
# Mukthi Guru — Frontend Dockerfile
# Multi-stage build: Node builder → Nginx static server
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests and install
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# --- Production stage ---
FROM nginx:1.27-alpine AS final

# Copy built static assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config if present (optional)
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
