# Welcome to your Lovable project

## Project info

**URL**: https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID

## How can I edit this code?

There are several ways of editing your application.

**Use Lovable**

Simply visit the [Lovable Project](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and start prompting.

Changes made via Lovable will be committed automatically to this repo.

**Use your preferred IDE**

If you want to work locally using your own IDE, you can clone this repo and push changes. Pushed changes will also be reflected in Lovable.

The only requirement is having Node.js & npm installed - [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating)

Follow these steps:

```sh
# Step 1: Clone the repository using the project's Git URL.
git clone <YOUR_GIT_URL>

# Step 2: Navigate to the project directory.
cd <YOUR_PROJECT_NAME>

# Step 3: Install the necessary dependencies.
npm i

# Step 4: Start the development server with auto-reloading and an instant preview.
npm run dev
```

**Edit a file directly in GitHub**

- Navigate to the desired file(s).
- Click the "Edit" button (pencil icon) at the top right of the file view.
- Make your changes and commit the changes.

## 🚀 How to Run (Docker)

The recommended way to run Mukthi Guru is via Docker Compose. This starts the Vector DB, Backend per, and Ingestion UI.

### Prerequisites
1. **Ollama**: Must be installed and running on your host machine.
   ```bash
   ollama serve
   ollama pull llama3.2:latest
   ```
2. **Docker Desktop**: Must be running.

### 1. Start the Stack
```bash
cd backend
docker compose up -d --build
```

### 2. Access the UIs
- **Ingestion Portal**: [http://localhost:8000/ingest/](http://localhost:8000/ingest/)
- **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Qdrant Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)

### 3. Ingest Content
1. Open the **Ingestion Portal** at [http://localhost:3001](http://localhost:3001).
2. Paste a YouTube video URL (e.g., `https://youtu.be/CvDkoctU5a4`).
3. (Optional) Check **Max Accuracy** to force high-quality transcription (Whisper) and skip auto-captions.
4. Click **Ingest**. The process runs in the background.

## ☁️ How to Run (Google Colab)

If you have limited local compute, you can run the full stack on Google Colab (Free Tier T4 GPU is supported).

1. **Open a new Colab Notebook**
2. **Clone the Repository**:
   ```python
   !git clone https://github.com/YourUsername/askmukthiguru.git
   %cd askmukthiguru/backend
   ```
3. **Run the Setup Script**:
   ```python
   !python colab/setup.py
   ```
   This script will:
   - Install dependencies (including `ffmpeg` and `ollama`)
   - Start Ollama and pull the model
   - Start the Backend (`localhost:8000`)
   - Serve Ingestion UI at `localhost:8000/ingest/`

4. **Accessing UIs (One Tunnel)**:
   Since Colab is remote, use **ngrok** to expose the backend port (8000):
   ```python
   from colab.setup import expose_with_ngrok
   expose_with_ngrok("YOUR_NGROK_AUTHTOKEN")
   ```
   - **Ingestion UI**: `https://<ngrok-url>/ingest/`
   - **API**: `https://<ngrok-url>/docs`
   
   *No extra 3001 port tunnel needed!*
   Or use the Colab "Port Forwarding" feature (VS Code style) if available in your interface.

5. **Backup & Restore (Persistence)**:
   To save your RAG data (vector DB) and models to Google Drive so you don't lose progress:
   ```python
   # Mount Drive and Backup
   !python colab/transfer.py backup --models
   
   # Restore from Drive (on next run)
   !python colab/transfer.py restore /content/drive/MyDrive/MukthiGuru_Backups/mukthiguru_backup_2024...zip
   ```



## 🛠 Directory Structure
- `backend/` — FastAPI application (RAG pipeline, LangGraph, Qdrant)
- `ingest-ui/` — Standalone Ingestion Frontend (HTML/JS)
- `src/` — Main React Application (Chat UI)

## 🐳 Services
| Service | URL | Description |
|---------|-----|-------------|
| **ingest-ui** | `:3001` | User interface for content ingestion |
| **backend** | `:8000` | Core API for Chat and Ingestion |
| **qdrant** | `:6333` | Vector Database |
| **ollama** | `:11434` | LLM Inference (Host) |

**Use GitHub Codespaces**

- Navigate to the main page of your repository.
- Click on the "Code" button (green button) near the top right.
- Select the "Codespaces" tab.
- Click on "New codespace" to launch a new Codespace environment.
- Edit files directly within the Codespace and commit and push your changes once you're done.

## What technologies are used for this project?

This project is built with:

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS

## How can I deploy this project?

Simply open [Lovable](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and click on Share -> Publish.

## Can I connect a custom domain to my Lovable project?

Yes, you can!

To connect a domain, navigate to Project > Settings > Domains and click Connect Domain.

Read more here: [Setting up a custom domain](https://docs.lovable.dev/features/custom-domain#custom-domain)
