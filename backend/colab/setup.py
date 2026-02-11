"""
Mukthi Guru — Google Colab Setup Script (Native Mode)

Runs everything directly on the Colab VM (no Docker required):
  - Ollama: installed natively for GPU access
  - Qdrant: runs in embedded/local mode (no server needed)
  - Backend: started directly via uvicorn

Usage in a Colab notebook:
  Cell 1:
    !git clone https://github.com/YOUR_REPO/askmukthiguru.git
    %cd askmukthiguru/backend

  Cell 2:
    !python colab/setup.py
"""

import subprocess
import sys
import os
import time


# ============================================================
# Step 1: Install Python Dependencies
# ============================================================

def install_dependencies():
    """Install backend Python dependencies from requirements.txt."""
    print("� Installing Python dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
        check=True,
    )
    # Install optional heavy deps needed for full functionality
    print("📦 Installing optional dependencies (whisper, easyocr)...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q",
         "openai-whisper>=20240930", "easyocr>=1.7.2"],
        check=False,  # Don't fail if these can't install
    )
    print("✅ Python dependencies installed")


# ============================================================
# Step 2: Install & Start Ollama (native, for GPU access)
# ============================================================

def setup_ollama(model: str = "llama3.2:latest"):
    """
    Install Ollama natively on the Colab VM.

    Runs directly on the VM to access Colab's T4 GPU.
    The backend connects to it via localhost:11434.

    Security: Downloads the install script to a temp file first,
    then verifies the download succeeded before executing.
    """
    import tempfile

    print("🦙 Installing Ollama...")

    # Install system dependency required by Ollama and Whisper
    subprocess.run(
        ["apt-get", "install", "-y", "-qq", "zstd", "ffmpeg"],
        check=False,  # Don't fail if apt isn't available (non-Colab)
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # Download script first (don't pipe curl into sh)
    script_path = os.path.join(tempfile.gettempdir(), "ollama_install.sh")
    dl_result = subprocess.run(
        ["curl", "-fsSL", "-o", script_path, "https://ollama.com/install.sh"],
        check=False,
    )
    if dl_result.returncode != 0:
        raise RuntimeError("Failed to download Ollama install script")

    # Verify file is non-empty
    if not os.path.exists(script_path) or os.path.getsize(script_path) < 100:
        raise RuntimeError("Ollama install script appears invalid or empty")

    # Execute the downloaded script
    subprocess.run(["sh", script_path], check=True)

    print("🚀 Starting Ollama server...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(5)

    print(f"📥 Pulling model: {model}")
    subprocess.run(["ollama", "pull", model], check=True)
    print(f"✅ Ollama ready with {model}")


# ============================================================
# Step 3: Configure Environment for Native Mode
# ============================================================

def configure_environment():
    """
    Write a .env file configured for native (non-Docker) mode.

    Key differences from Docker mode:
    - Qdrant uses local/embedded mode (no server) via QDRANT_LOCAL_PATH
    - Ollama is on localhost (not host.docker.internal)
    """
    env_path = os.path.join(os.getcwd(), ".env")

    env_content = """\
# === Mukthi Guru — Colab Native Mode ===

# Ollama (running natively on this VM)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=ajindal/llama3.1-storm:8b

# Qdrant — embedded/local mode (no server needed)
# Data persists to this directory on disk
QDRANT_LOCAL_PATH=./qdrant_data
QDRANT_COLLECTION=spiritual_wisdom
# QDRANT_URL is ignored when QDRANT_LOCAL_PATH is set

# Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# Server
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=*
"""
    with open(env_path, "w") as f:
        f.write(env_content)

    print(f"✅ Environment configured: {env_path}")
    print("   Qdrant mode: embedded (./qdrant_data)")
    print("   Ollama: localhost:11434")





# ============================================================
# Step 5: Start the Backend
# ============================================================

def start_backend():
    """
    Start the FastAPI backend directly via uvicorn.

    Runs in the background so the Colab cell completes.
    The server is accessible at http://localhost:8000.
    """
    print("🚀 Starting FastAPI backend...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for the server to start, polling health endpoint
    print("⏳ Waiting for backend to be ready...")
    for attempt in range(30):
        time.sleep(2)
        try:
            result = subprocess.run(
                ["curl", "-sf", "http://localhost:8000/api/health"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print("✅ Backend is running!")
                return proc
        except Exception:
            pass

    # If we get here, server didn't start — show logs
    print("⚠️  Backend may not be ready yet. Checking logs...")
    if proc.poll() is not None:
        stdout = proc.stdout.read().decode() if proc.stdout else ""
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        print(f"   Exit code: {proc.returncode}")
        print(f"   Stdout: {stdout[:500]}")
        print(f"   Stderr: {stderr[:500]}")
    else:
        print("   Server process is still running — it may need more time.")
        print("   Try: !curl http://localhost:8000/api/health")

    return proc


# ============================================================
# Step 5: Expose with ngrok (optional)
# ============================================================

def expose_with_ngrok(auth_token: str = ""):
    """Expose the backend via ngrok tunnel."""
    if not auth_token:
        print("⚠️  No ngrok token provided. Backend available at http://localhost:8000")
        return

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "pyngrok==7.2.2"],
        check=True,
    )

    from pyngrok import ngrok, conf
    conf.get_default().auth_token = auth_token
    tunnel = ngrok.connect(8000)
    print(f"\n🌐 Public URL: {tunnel.public_url}")
    print(f"🖥️  Ingest UI: {tunnel.public_url}/ingest/")
    print(f"📋 Set in frontend: {tunnel.public_url}/api/chat")


# ============================================================
# Step 6: Ingest Content
# ============================================================

def ingest_content(url: str):
    """Ingest content via the running API."""
    import json
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "http://localhost:8000/api/ingest",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"url": url}),
             "--max-time", "300"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"❌ Ingestion request failed (exit code {result.returncode})")
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}")
            return

        response_text = result.stdout.strip()
        if not response_text:
            print("⚠️  Ingestion returned empty response — is the server running?")
            return

        try:
            response = json.loads(response_text)
            print(f"Ingestion response: {json.dumps(response, indent=2)}")
        except json.JSONDecodeError:
            print(f"Ingestion response (raw): {response_text[:500]}")
    except Exception as e:
        print(f"❌ Ingestion failed: {e}")


# ============================================================
# Main: Run All Steps
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🙏 Mukthi Guru — Native Colab Setup")
    print("=" * 60)

    install_dependencies()
    setup_ollama()
    configure_environment()
    backend_proc = start_backend()

    print("\n" + "=" * 60)
    print("  ✅ Setup complete!")
    print("=" * 60)
    print("   Health: curl http://localhost:8000/api/health")
    print("   Chat:   POST http://localhost:8000/api/chat")
    print("   Ingest: http://localhost:8000/ingest/")
    print("\n   To expose publicly:")
    print("     from colab.setup import expose_with_ngrok")
    print("     expose_with_ngrok('YOUR_NGROK_TOKEN')")
