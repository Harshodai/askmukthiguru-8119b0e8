# ============================================================
# AskMukthiGuru — Frontend Dockerfile
# Multi-stage: build React app with Vite, serve with Nginx
# ============================================================

# --- Stage 1: Build the React app ---
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# Copy source code and build
COPY index.html vite.config.ts tsconfig*.json tailwind.config.ts postcss.config.js components.json ./
COPY src/ ./src/
COPY public/ ./public/ 2>/dev/null || true

# Build for production
RUN npm run build

# --- Stage 2: Serve with Nginx ---
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy the built React app
COPY --from=builder /app/dist /usr/share/nginx/html/app

# Copy static UI folders (lightweight chat & ingest widgets)
COPY ingest-ui/ /usr/share/nginx/html/ingest/
COPY chat-ui/ /usr/share/nginx/html/chat/

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
