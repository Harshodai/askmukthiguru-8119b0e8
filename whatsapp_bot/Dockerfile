FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wa_bot.py .

# Persist SQLite to a volume; mount at /data in production
ENV WA_DB_PATH=/data/wa_state.db
VOLUME ["/data"]

EXPOSE 8080

# Production server (Twilio webhooks tolerate gunicorn just fine)
RUN pip install --no-cache-dir gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout", "90", "wa_bot:app"]
