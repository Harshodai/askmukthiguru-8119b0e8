# ============================================================
# Mukthi Guru — Frontend Dockerfile
# Multi-stage build: Vite → Nginx static serving
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (cache layer)
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# --- Final stage: Nginx ---
FROM nginx:1.25-alpine

# Copy built static files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx config for SPA routing
COPY k8s/nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]