# ============================================================
# AskMukthiGuru — Frontend Dockerfile
# Multi-stage: build React app with Vite, serve with Nginx
# ============================================================

# --- Stage 1: Build the React app ---
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm install

# Build arguments for environment variables
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ARG VITE_USE_NATIVE_OAUTH

# Set them as environment variables for the build process
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY
ENV VITE_USE_NATIVE_OAUTH=$VITE_USE_NATIVE_OAUTH

# Copy source code and build
COPY index.html vite.config.ts tsconfig*.json tailwind.config.ts postcss.config.js components.json ./
COPY src/ ./src/
COPY public/ ./public/

# Build for production
RUN NODE_OPTIONS="--max-old-space-size=4096" npm run build

# --- Stage 2: Serve with Nginx ---
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy the built React app
COPY --from=builder /app/dist /usr/share/nginx/html/app

# Copy static UI folders (lightweight chat & ingest widgets) - Renamed to avoid shadowing React routes
COPY ingest-ui/ /usr/share/nginx/html/static-ingest/
COPY chat-ui/ /usr/share/nginx/html/static-chat/

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
