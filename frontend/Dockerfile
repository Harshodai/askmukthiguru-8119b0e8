# ============================================================
# Mukthi Guru — Frontend Dockerfile
# Multi-stage build: Node builder → Nginx static server
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests and install
COPY package.json package-lock.json ./
RUN npm ci

# Supabase values are baked into the bundle at build time and have no defaults:
# a build without them fails loudly instead of shipping the wrong project.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY
# Feature flags mirror backend/docker-compose.yml args; each must be declared
# here or Docker silently drops it (that exact miss kept /teachers-words
# 404 locally despite the compose default of true).
ARG VITE_FIRST_PERSON_ENABLED=true
ENV VITE_FIRST_PERSON_ENABLED=$VITE_FIRST_PERSON_ENABLED

RUN [ -n "$VITE_SUPABASE_URL" ] || { echo "ERROR: VITE_SUPABASE_URL build argument is required and cannot be empty"; exit 1; } && \
    [ -n "$VITE_SUPABASE_PUBLISHABLE_KEY" ] || { echo "ERROR: VITE_SUPABASE_PUBLISHABLE_KEY build argument is required and cannot be empty"; exit 1; }

# Copy source and build
COPY . .
RUN npm run build

# --- Production stage ---
# 1.27's Alpine base carries 43 fixable HIGH/CRITICAL (openssl, expat, libpng, ...);
# 1.30 is the current stable line. nginx.conf validated with `nginx -t` on 1.30-alpine.
FROM nginx:1.30-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94 AS final

# Pick up Alpine security fixes published after the base image was built
# (libexpat, pcre2, tiff were fixable HIGHs on 2026-10-13).
RUN apk upgrade --no-cache

# Copy built static assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config if present (optional)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
