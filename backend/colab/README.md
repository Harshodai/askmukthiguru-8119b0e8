# Mukthi Guru — Google Colab Guide 🚀

This guide explains how to run the full **Mukthi Guru** stack (Backend + AI + Ingestion UI) entirely within Google Colab using a single setup script.

## 📋 Prerequisites
- **Google Account**
- **Google Colab** (Free tier works, but Pro is recommended for longer sessions)
- **Runtime Type**: Python 3 + **T4 GPU** (Required for Ollama/Whisper)
- **Ngrok Account**: Free account to expose the UI/API to the internet.

---

## 🚀 Step-by-Step Setup

### 1. Open Colab & Connect to GPU
1. Create a new Notebook.
2. Go to **Runtime** > **Change runtime type**.
3. Select **T4 GPU**.

### 2. Clone the Repository
Run this in the first cell:
```python
!git clone https://github.com/YourUsername/askmukthiguru.git
%cd askmukthiguru/backend
```

### 3. Run the "Everything" Setup Script
This single script installs Python dependencies, installs/starts Ollama (AI), configures Qdrant (Database), and launches the Backend server.
```python
!python colab/setup.py
```
*Wait until you see "✅ Backend is running!".*

### 4. Expose to the Internet
To access the UI and API, you need a public URL. Use the helper function with your [Ngrok Authtoken](https://dashboard.ngrok.com/get-started/your-authtoken).

```python
from colab.setup import expose_with_ngrok

# Replace with your actual token
expose_with_ngrok("YOUR_NGROK_TOKEN_HERE")
```

**Output will look like:**
> 🌐 Public URL: https://a1b2c3d4.ngrok.app
> 🖥️ Ingest UI: https://a1b2c3d4.ngrok.app/ingest/

---

## 🏗️ Architecture Explained

To make Colab deployment easy, we consolidated everything:
1.  **Unified Backend**: The FastAPI backend (`port 8000`) now **also serves the Ingestion UI** (at `/ingest/`). No need for a separate Node.js server.
2.  **Native Ollama**: We install Ollama directly on the Colab VM to use the GPU.
3.  **Local Qdrant**: The Vector DB runs in "embedded" mode, saving data to `./qdrant_data` on disk, avoiding a separate Docker container.

All of this runs inside the Colab environment, and **Ngrok** tunnels port 8000 to the world.

---

## 🔗 How to Use

### 1. Ingestion Portal
Click the **Ingest UI** link from step 4 (e.g., `https://.../ingest/`).
- **Submit URLs**: Paste a YouTube video or playlist URL.
- **Track Progress**: A progress bar will appear.
- **Status**: Watch the health indicator (top right).

### 2. Connect Your App
If you have a mobile or web app (Flutter/React), update its API Base URL to the Ngrok Public URL.
```typescript
const API_BASE = "https://a1b2c3d4.ngrok.app";
```

### 3. Save Your Progress (Critical!) 💾
Colab recycles environments. To save your ingested knowledge base:
1.  Mount Google Drive:
    ```python
    from google.colab import drive
    drive.mount('/content/drive')
    ```
2.  Run the transfer script to backup `qdrant_data`:
    ```python
    !python colab/transfer.py backup
    ```
    This creates `backup.zip` in your Drive.
3.  To restore next time:
    ```python
    !python colab/transfer.py restore
    ```

---

## 📡 Sample API Commands (cURL)

You can test the API directly from a local terminal using the Ngrok URL.

#### Health Check
```bash
curl https://YOUR_NGROK_URL/api/health
```

#### Ingest a Video
```bash
curl -X POST https://YOUR_NGROK_URL/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtu.be/ExampleVideoId", "max_accuracy": false}'
```

#### Check Ingestion Status
```bash
curl https://YOUR_NGROK_URL/api/ingest/status
```

#### Chat / Query
```bash
curl -X POST https://YOUR_NGROK_URL/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "How do I find peace?"}],
    "stream": false
  }'
```
