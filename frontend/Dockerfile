# ============================================================
# Mukthi Guru — Frontend Dockerfile
# Multi-stage build: Node 24 builder -> non-root Nginx static server
# ============================================================

FROM node:24-alpine AS builder

WORKDIR /app

# Copy package manifests and install deterministically
COPY package.json package-lock.json ./
RUN npm ci

# Supabase & feature flags baked into the Vite bundle at build time
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ARG VITE_FIRST_PERSON_ENABLED=true
ARG VITE_PERSONALIZE_TEACHING_ENABLED=false
ARG VITE_BACKEND_URL=""
ARG VITE_GOOGLE_CLIENT_ID=""
ARG VITE_USE_NATIVE_OAUTH=false
ARG VITE_ADMIN_ENABLED=true
ARG VITE_ALLOWED_EMAIL_DOMAINS=""

ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY \
    VITE_FIRST_PERSON_ENABLED=$VITE_FIRST_PERSON_ENABLED \
    VITE_PERSONALIZE_TEACHING_ENABLED=$VITE_PERSONALIZE_TEACHING_ENABLED \
    VITE_BACKEND_URL=$VITE_BACKEND_URL \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_USE_NATIVE_OAUTH=$VITE_USE_NATIVE_OAUTH \
    VITE_ADMIN_ENABLED=$VITE_ADMIN_ENABLED \
    VITE_ALLOWED_EMAIL_DOMAINS=$VITE_ALLOWED_EMAIL_DOMAINS

RUN [ -n "$VITE_SUPABASE_URL" ] || { echo "ERROR: VITE_SUPABASE_URL build argument is required and cannot be empty"; exit 1; } && \
    [ -n "$VITE_SUPABASE_PUBLISHABLE_KEY" ] || { echo "ERROR: VITE_SUPABASE_PUBLISHABLE_KEY build argument is required and cannot be empty"; exit 1; }

COPY . .
RUN npm run build

# --- Production stage ---
FROM nginx:1.30-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94 AS final

RUN apk upgrade --no-cache

# Match nginx.conf root (/usr/share/nginx/html/app) and run as non-root nginx user
COPY --from=builder /app/dist /usr/share/nginx/html/app
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
