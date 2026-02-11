"""
Mukthi Guru — Google Colab Setup Script (Docker-based)

This script containerizes the backend using Docker on Colab.
Ollama runs natively on the Colab VM for GPU access.

Usage on Colab:
  !git clone https://github.com/YOUR_REPO/askmukthiguru.git
  %cd askmukthiguru/backend
  !python colab/setup.py
"""

import subprocess
import sys
import os
import time


# ============================================================
# Cell 1: Install Docker on Colab
# ============================================================

def install_docker():
    """Install Docker Engine on the Colab VM."""
    print("🐳 Installing Docker...")
    commands = [
        "apt-get update -qq",
        "apt-get install -y -qq docker.io docker-compose-plugin > /dev/null",
        "dockerd &",  # Start Docker daemon
    ]
    for cmd in commands:
        subprocess.run(cmd, shell=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)  # Wait for dockerd to start
    subprocess.run("docker info > /dev/null 2>&1", shell=True, check=True)
    print("✅ Docker installed and running")


# ============================================================
# Cell 2: Install & Start Ollama (native, for GPU access)
# ============================================================

def setup_ollama(model: str = "llama3.2:latest"):
    """
    Install Ollama natively on the Colab VM.
    
    Runs OUTSIDE Docker to access Colab's GPU directly.
    The Docker containers reach it via host.docker.internal.
    
    Security: Downloads the install script to a temp file first,
    then verifies the download succeeded before executing.
    """
    import tempfile

    print("🦙 Installing Ollama...")
    
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
# Cell 3: Start Full Stack with Docker Compose
# ============================================================

def start_stack():
    """
    Start Qdrant + Backend using Docker Compose.
    
    The docker-compose.yml already configures:
    - Qdrant with persistent volume
    - Backend connecting to host Ollama via host.docker.internal
    """
    print("🚀 Starting Docker Compose stack...")
    subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        check=True,
    )

    # Wait for health checks
    print("⏳ Waiting for services to be healthy...")
    time.sleep(30)

    # Check service status
    subprocess.run(["docker", "compose", "ps"], check=True)
    print("✅ Stack is running!")


# ============================================================
# Cell 4: Expose with ngrok
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
    print(f"📋 Set in frontend: {tunnel.public_url}/api/chat")


# ============================================================
# Cell 5: Ingest Content
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
             "--max-time", "10"],
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
    print("  🙏 Mukthi Guru — Docker-based Colab Setup")
    print("=" * 60)

    # Detect if running on Colab
    on_colab = os.path.exists("/content")

    if on_colab:
        install_docker()

    setup_ollama()
    start_stack()

    print("\n✅ Setup complete!")
    print("   Health: curl http://localhost:8000/api/health")
    print("   Chat:   POST http://localhost:8000/api/chat")
    print("   Ingest: POST http://localhost:8000/api/ingest")

    if on_colab:
        print("\n   Run expose_with_ngrok('YOUR_TOKEN') for public access")
