FROM python:3.11-slim

# Create non-root user
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY wa_bot.py .

# Persist SQLite to a volume; mount at /data in production
RUN mkdir -p /data && chown appuser:appuser /data
ENV WA_DB_PATH=/data/wa_state.db
VOLUME ["/data"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import http.client; conn=http.client.HTTPConnection('localhost',8080,timeout=5); conn.request('GET','/'); conn.getresponse()" || exit 1

USER appuser

CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout", "90", "wa_bot:app"]
