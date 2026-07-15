import os
import subprocess
import sys

service_type = os.environ.get("SERVICE_TYPE", "api").lower()

if service_type == "celery":
    print("Starting Celery worker service...")
    cmd = [
        "celery",
        "-A", "celery_config.celery_app",
        "worker",
        "--loglevel=info",
        "-Q", "transcription,embedding,indexing,ingestion,okf"
    ]
else:
    print("Starting FastAPI web api service...")
    port = os.environ.get("PORT", "8000")
    workers = os.environ.get("WEB_CONCURRENCY", "1")  # 1 worker per replica — BGE-M3 (~550MB) makes 2+ OOMKill
    cmd = [
        "python", "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--workers", workers
    ]

# Exec the process to pass signals properly
try:
    os.execvp(cmd[0], cmd)
except AttributeError:
    # Fallback for platforms where execvp doesn't behave or is missing (like Windows local dev)
    sys.exit(subprocess.call(cmd))
