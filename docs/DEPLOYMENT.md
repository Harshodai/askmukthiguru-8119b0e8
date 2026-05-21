# 🚀 Mukthi Guru — Deployment Guide

Complete guide for running Mukthi Guru with Sarvam 30B, from local dev to cheap production.

> [!IMPORTANT]
> **Sarvam 30B** is a Mixture-of-Experts (MoE) model — 32B total params but only **2.4B active**.
> This means it runs much faster and lighter than a typical 30B model.
> With Q4 quantization: **~18GB VRAM** needed (fits on a single RTX 4090 or A100).

---

## 📋 Prerequisites

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 16 GB (CPU offload) | 24 GB (full GPU) |
| RAM | 16 GB | 32 GB |
| Disk | 30 GB free | 50 GB free |
| OS | Windows 10+, Ubuntu 20.04+, macOS 13+ | Linux (Ubuntu 22.04) |

---

## 🖥️ Option 1: Local Development (Your Machine)

### Step 1: Install Ollama

```bash
# Windows: Download from https://ollama.com/download
# Linux:
curl -fsSL https://ollama.com/install.sh | sh
# macOS:
brew install ollama
```

### Step 2: Download the Models

```bash
# Start Ollama server
ollama serve

# In a new terminal — download models using the unified script
cd backend/models

# Option A: Qwen preset (DEFAULT — works with native ollama pull)
./download_models.sh qwen
# Downloads: qwen3:30b-a3b (~18 GB) + qwen3:14b (~10 GB)

# Option B: Sarvam preset (downloads GGUF from HuggingFace + imports)
./download_models.sh sarvam
# Downloads: sarvam-30b (~19 GB GGUF) + llama3.2:3b (~2 GB)

# Option C: Both presets
./download_models.sh all

# Windows:
# .\download_models.ps1 qwen    # or sarvam, or all
```

> [!NOTE]
> Sarvam 30B is **NOT** on the Ollama registry — it requires downloading a GGUF from
> HuggingFace (`Sumitc13/sarvam-30b-GGUF`) and importing via Modelfile.
> The `download_models.sh sarvam` command handles this automatically.

### Step 3: Start Qdrant (Docker)

```bash
cd backend
docker compose up qdrant -d
```

### Step 4: Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env if needed (defaults should work for local)

# Start the backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 5: Start Frontend

```bash
# In the project root (separate terminal)
npm install
npm run dev
```

### Step 6: Ingest Content

Open `http://localhost:8000/ingest` and paste YouTube URLs to index.

✅ **Done!** Your app is running at `http://localhost:5173`

---

## ☁️ Option 2: Google Colab (Free GPU — for Testing)

> [!WARNING]
> Colab T4 has only **15 GB VRAM** — Sarvam 30B will need CPU offloading and run slower.
> For best results, use Colab **A100** (Pro/Pro+) which has 40-80 GB VRAM.

```bash
# Just run the setup script — it handles everything
python colab/setup.py
```

The Colab setup automatically:
1. Installs Ollama natively (for GPU access)
2. Pulls Sarvam 30B
3. Starts Qdrant in embedded mode (no Docker needed)
4. Launches the backend

---

## 🏭 Option 3: Production (Cheap Cloud GPU)

### Cheapest Options Compared (2025)

| Provider | GPU | VRAM | $/hour | $/month (24/7) | Best For |
|----------|-----|------|--------|---------|---------|
| **Vast.ai** | RTX 4090 | 24 GB | $0.28 | ~$200 | Cheapest, hobbyist |
| **RunPod** | RTX 4090 | 24 GB | $0.39 | ~$280 | Balanced reliability |
| **RunPod** | A100 80GB | 80 GB | $1.19 | ~$860 | Premium performance |
| **Lambda** | A100 80GB | 80 GB | $1.79 | ~$1,290 | Enterprise |

> [!TIP]
> **Budget pick: Vast.ai RTX 4090 at $0.28/hr (~$200/month)**
> Sarvam 30B (MoE, only 2.4B active) runs great on a single 24 GB GPU.

### Step-by-Step: Deploy on Vast.ai (Cheapest)

#### 1. Get a GPU Instance

1. Go to [vast.ai](https://vast.ai) → Create account
2. Click **Search** → Filter:
   - GPU: `RTX 4090` (24 GB)
   - Disk: `50 GB`
   - Image: `nvidia/cuda:12.4.0-runtime-ubuntu22.04`
3. Pick the cheapest instance → **Rent**
4. Connect via SSH

#### 2. Setup on the GPU Server

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &

# Wait for Ollama to start, then download models
sleep 5

# Clone the repo first (need the download scripts)
git clone https://github.com/YOUR_USER/askmukthiguru.git
cd askmukthiguru/backend/models

# Download models based on preset
./download_models.sh ${MODEL_PRESET:-qwen}
cd ../..

# Install Docker (for Qdrant)
curl -fsSL https://get.docker.com | sh

# Start Qdrant
docker compose up qdrant -d

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure for production
cp .env.example .env
# Edit .env:
#   HOST=0.0.0.0
#   CORS_ORIGINS=https://yourdomain.com
```

#### 3. Run in Production

```bash
# Production mode with Gunicorn (multi-worker)
pip install gunicorn
gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 2 \
    --bind 0.0.0.0:8000 \
    --timeout 120
```

#### 4. Keep It Running (tmux/systemd)

```bash
# Option A: tmux (simple)
tmux new -s guru
# Run the gunicorn command above, then Ctrl+B, D to detach

# Option B: systemd (robust)
sudo tee /etc/systemd/system/mukthiguru.service << 'EOF'
[Unit]
Description=Mukthi Guru Backend
After=network.target docker.service

[Service]
User=root
WorkingDirectory=/root/askmukthiguru/backend
Environment="PATH=/root/askmukthiguru/backend/venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/root/askmukthiguru/backend/venv/bin/gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 2 \
    --bind 0.0.0.0:8000 \
    --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mukthiguru
sudo systemctl start mukthiguru
```

---

### Step-by-Step: Deploy on RunPod (Reliable)

#### 1. Create a Pod

1. Go to [runpod.io](https://runpod.io) → Create account
2. **Deploy** → **GPU Pod** → Select `RTX 4090` (community: $0.39/hr)
3. Template: `RunPod Pytorch 2.4` or any Ubuntu-based template
4. Disk: 50 GB → **Deploy**
5. Connect via **Web Terminal** or SSH

#### 2. Same Setup Commands

```bash
# Same steps as Vast.ai above — install Ollama, Docker, clone repo, etc.
curl -fsSL https://ollama.com/install.sh | sh
# ... (same commands)
```

> [!NOTE]  
> RunPod supports **persistent volumes** — your models and data survive pod restarts.
> Attach a persistent volume to `/root` to avoid re-downloading Sarvam 30B on restart.

---

## 💡 Cost-Saving Tips

### Run Only When Needed
If your app doesn't need 24/7 uptime, start/stop the GPU instance on demand:
```bash
# Vast.ai: Use their CLI
vastai stop instance $INSTANCE_ID   # ~$0 when stopped
vastai start instance $INSTANCE_ID  # Resume

# RunPod: Stop/start from dashboard (only pay for storage when stopped)
```

### Use Spot/Interruptible Instances  
Both Vast.ai and RunPod offer interruptible instances at **50-70% discount**.
Good for dev/testing, not recommended for production.

### Frontend on Vercel (Free)
Host the Next.js/Vite frontend on **Vercel** or **Netlify** for free:
```bash
# Deploy frontend
npm run build
# Push to GitHub → Connect to Vercel → Auto-deploy
```
Set `VITE_API_URL` to your GPU server's public IP:
```
VITE_API_URL=http://YOUR_GPU_SERVER_IP:8000
```

### Use the Fast Classifier Aggressively
The `llama3.2:3b` classification model runs 10x faster than Sarvam 30B.
It handles intent classification, relevance grading, and complexity checks —
keeping the expensive Sarvam 30B calls to a minimum (generation + verification only).

---

## 🔧 Environment Variables Quick Reference

```bash
# Required for any deployment
MODEL_PRESET=qwen                          # "qwen" (default), "sarvam", or "custom"
OLLAMA_BASE_URL=http://localhost:11434     # or http://host.docker.internal:11434 in Docker
QDRANT_URL=http://localhost:6333

# Only needed for MODEL_PRESET=custom (otherwise auto-resolved from preset):
# OLLAMA_MODEL=sarvam-30b:latest
# OLLAMA_CLASSIFY_MODEL=llama3.2:3b

# Production security
CORS_ORIGINS=https://yourdomain.com       # Don't use * in production
HOST=0.0.0.0
PORT=8000
```

---

## 📊 Expected Performance

| Metric | RTX 4090 (24GB) | A100 (80GB) | T4 (16GB, Colab) |
|--------|----------------|-------------|-------------------|
| Classification (3B) | ~0.3s | ~0.2s | ~0.8s |
| Generation (30B) | ~3-5s | ~1-2s | ~8-15s (CPU offload) |
| Full pipeline | ~8-12s | ~4-6s | ~20-30s |
| Concurrent users | 3-5 | 10-20 | 1 |

> [!NOTE]
> These are estimates. Sarvam 30B is a MoE model with only 2.4B active parameters,
> so it's significantly faster than a full 30B dense model.
