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

def setup_ollama(preset: str = "qwen"):
    """
    Install Ollama natively on the Colab VM and pull models based on preset.

    Runs directly on the VM to access Colab's T4 GPU.
    The backend connects to it via localhost:11434.

    Presets:
      - "qwen":  qwen3:30b-a3b (gen) + qwen3:14b (classify)
      - "sarvam": sarvam-30b via GGUF import + llama3.2:3b (classify)
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

    # Model presets
    PRESETS = {
        "qwen": {
            "generation": "qwen3:30b-a3b",
            "classification": "qwen3:14b",
        },
        "sarvam": {
            "generation": "sarvam-30b:latest",  # Imported via GGUF below
            "classification": "llama3.2:3b",
        },
    }

    preset_config = PRESETS.get(preset.lower(), PRESETS["qwen"])
    gen_model = preset_config["generation"]
    cls_model = preset_config["classification"]

    if preset.lower() == "sarvam":
        # Sarvam requires GGUF download + Modelfile import
        print("📥 Setting up Sarvam 30B (GGUF import)...")
        _setup_sarvam_gguf()
    else:
        # Qwen models are on the Ollama registry
        print(f"📥 Pulling generation model: {gen_model}")
        subprocess.run(["ollama", "pull", gen_model], check=True)

    print(f"📥 Pulling classification model: {cls_model}")
    subprocess.run(["ollama", "pull", cls_model], check=True)

    print(f"✅ Ollama ready (preset: {preset})")
    print(f"   Generation: {gen_model}")
    print(f"   Classification: {cls_model}")
    return gen_model, cls_model


def _setup_sarvam_gguf():
    """
    Download Sarvam 30B GGUF from HuggingFace and import into Ollama.
    Used when MODEL_PRESET=sarvam.
    """
    HF_REPO = "Sumitc13/sarvam-30b-GGUF"
    GGUF_FILENAME = "sarvam-30B-Q4_K_M.gguf"
    MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

    # Install huggingface-cli if needed
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "huggingface_hub[cli]"],
        check=True,
    )

    gguf_path = os.path.join(MODELS_DIR, GGUF_FILENAME)
    if os.path.exists(gguf_path):
        print(f"   ✅ GGUF already exists: {GGUF_FILENAME}")
    else:
        print(f"   📥 Downloading GGUF from {HF_REPO} (~19GB)...")
        subprocess.run(
            ["huggingface-cli", "download", HF_REPO, GGUF_FILENAME,
             "--local-dir", MODELS_DIR, "--local-dir-use-symlinks", "False"],
            check=True,
        )

    # Import via Modelfile
    modelfile_path = os.path.join(MODELS_DIR, "Modelfile.sarvam30b")
    if os.path.exists(modelfile_path):
        print("   🔧 Importing into Ollama via Modelfile...")
        subprocess.run(
            ["ollama", "create", "sarvam-30b", "-f", modelfile_path],
            check=True,
        )
        print("   ✅ Sarvam 30B imported into Ollama")
    else:
        print(f"   ❌ Modelfile not found at {modelfile_path}")
        raise FileNotFoundError(f"Missing: {modelfile_path}")


# ============================================================
# Step 3: Configure Environment for Native Mode
# ============================================================

def configure_environment(preset: str = "qwen"):
    """
    Write a .env file configured for native (non-Docker) mode.

    Key differences from Docker mode:
    - Qdrant uses local/embedded mode (no server) via QDRANT_LOCAL_PATH
    - Ollama is on localhost (not host.docker.internal)
    - Model preset is set from the argument
    """
    env_path = os.path.join(os.getcwd(), ".env")

    env_content = f"""\
# === Mukthi Guru — Colab Native Mode ===

# Model Preset: "qwen" or "sarvam"
MODEL_PRESET={preset}

# Ollama (running natively on this VM)
OLLAMA_BASE_URL=http://localhost:11434

# Qdrant — embedded/local mode (no server needed)
# Data persists to this directory on disk
QDRANT_LOCAL_PATH=./qdrant_data
QDRANT_COLLECTION=spiritual_wisdom
# QDRANT_URL is ignored when QDRANT_LOCAL_PATH is set

# Embeddings
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# Server
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=*
"""
    with open(env_path, "w") as f:
        f.write(env_content)

    print(f"✅ Environment configured: {env_path}")
    print(f"   Model preset: {preset}")
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
    print("🚀 Starting FastAPI backend (logs -> backend.log)...")
    log_file = open("backend.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
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
    """
    Expose the backend via ngrok tunnel and auto-open UI in Colab.
    """
    if not auth_token:
        print("⚠️  No ngrok token provided. Backend available at http://localhost:8000")
        return

    try:
        from pyngrok import ngrok, conf
        from IPython.display import display, Javascript, HTML
    except ImportError:
        # Install if missing (just in case)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "pyngrok==7.2.2"],
            check=True,
        )
        from pyngrok import ngrok, conf
        try:
            from IPython.display import display, Javascript, HTML
        except ImportError:
            display = print # Fallback

    print("🔌 Starting Ngrok tunnel...")
    
    # 1. Kill old tunnels to avoid "too many sessions" error on free tier
    ngrok.kill()
    
    # 2. Connect
    conf.get_default().auth_token = auth_token
    tunnel = ngrok.connect(8000)
    public_url = tunnel.public_url
    ingest_url = f"{public_url}/ingest/"
    docs_url = f"{public_url}/docs"

    # 3. Text Output
    print(f"\n✨ Ngrok Tunnel Established! ✨")
    print(f"👉 INGEST UI: {ingest_url}")
    print(f"📄 API DOCS:  {docs_url}")

    # 4. Colab Rich Output (Clickable Button + Auto Open)
    if 'google.colab' in sys.modules:
        html_content = f"""
        <div style="
            border: 2px solid #4CAF50; 
            padding: 20px; 
            border-radius: 10px; 
            background: #1e1e1e; 
            color: white; 
            font-family: sans-serif;
            margin-top: 10px;">
            <h2 style="margin-top:0; color: #4CAF50;">🚀 Mukthi Guru is Live!</h2>
            <p>Click below to open the Ingestion Portal:</p>
            <a href="{ingest_url}" target="_blank" style="
                background-color: #4CAF50;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 16px;
                display: inline-block;
                transition: background 0.3s;">
                Open Ingestion UI ↗️
            </a>
            <p style="margin-top:15px; font-size: 12px; color: #aaa;">
                Backend URL: {public_url}<br>
                API Docs: <a href="{docs_url}" target="_blank" style="color: #64B5F6;">{docs_url}</a>
            </p>
        </div>
        """
        display(HTML(html_content))
        # Attempt auto-open
        display(Javascript(f'window.open("{ingest_url}", "_blank");'))


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

    # Read preset from env or default to qwen
    preset = os.environ.get("MODEL_PRESET", "qwen").lower()
    print(f"   Model preset: {preset}")
    print("")

    install_dependencies()
    setup_ollama(preset)
    configure_environment(preset)
    backend_proc = start_backend()
    
    # Auto-expose if NGROK_AUTH_TOKEN is set in environment
    ngrok_token = os.environ.get("NGROK_AUTH_TOKEN", "")
    if ngrok_token:
        print("\n" + "=" * 60)
        print("  🌍 Exposing to Internet (Auto)")
        print("=" * 60)
        expose_with_ngrok(ngrok_token)
    else:
        print("\n⚠️  Set NGROK_AUTH_TOKEN env var to auto-expose via ngrok.")
        print("   Backend available locally at http://localhost:8000")
