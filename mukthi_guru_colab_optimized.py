# 🕉️ MUKTHI GURU v5.0: OPTIMIZED COLAB EDITION (T4 GPU SAFE)
# Features: Sarvam 2B (Indian Multilingual), faster-whisper large-v3,
#           4-Tier Transcripts, Concurrent Ingestion, VRAM Management,
#           Robust Persistence, Enhanced RAG

import os
import sys
import shutil
import time
import asyncio
import re
import tempfile
import subprocess
import gc
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. ROBUST PERSISTENCE & CACHING
# ==========================================
print("📂 Initializing Persistence Layer...")

DRIVE_MOUNT_POINT = "/content/drive"
DRIVE_ROOT = f"{DRIVE_MOUNT_POINT}/MyDrive/MukthiGuru_v5"
CACHE_ROOT = f"{DRIVE_ROOT}/cache"

PIP_CACHE = f"{CACHE_ROOT}/pip"
HF_CACHE = f"{CACHE_ROOT}/huggingface"
TORCH_CACHE = f"{CACHE_ROOT}/torch"
QDRANT_PATH = f"{DRIVE_ROOT}/qdrant_db"

def setup_drive():
    if not os.path.exists(DRIVE_MOUNT_POINT):
        os.makedirs(DRIVE_MOUNT_POINT, exist_ok=True)

    if not os.path.exists(f"{DRIVE_MOUNT_POINT}/MyDrive"):
        try:
            from google.colab import drive
            print("  🔗 Mounting Google Drive...")
            drive.mount(DRIVE_MOUNT_POINT)
        except ImportError:
            print("  ⚠️ Not running in Colab. Using local storage.")
            global DRIVE_ROOT, CACHE_ROOT, QDRANT_PATH, PIP_CACHE, HF_CACHE, TORCH_CACHE
            DRIVE_ROOT = "./MukthiGuru_v5_Local"
            CACHE_ROOT = f"{DRIVE_ROOT}/cache"
            PIP_CACHE = f"{CACHE_ROOT}/pip"
            HF_CACHE = f"{CACHE_ROOT}/huggingface"
            TORCH_CACHE = f"{CACHE_ROOT}/torch"
            QDRANT_PATH = f"{DRIVE_ROOT}/qdrant_db"

    for folder in [DRIVE_ROOT, CACHE_ROOT, PIP_CACHE, HF_CACHE, TORCH_CACHE, QDRANT_PATH]:
        os.makedirs(folder, exist_ok=True)

    system_hf_home = os.path.expanduser("~/.cache/huggingface")
    if not os.path.islink(system_hf_home) and os.path.exists(system_hf_home):
        shutil.rmtree(system_hf_home)
    if not os.path.exists(system_hf_home):
        os.makedirs(os.path.dirname(system_hf_home), exist_ok=True)
        os.symlink(HF_CACHE, system_hf_home)

    os.environ['HF_HOME'] = HF_CACHE
    os.environ['TORCH_HOME'] = TORCH_CACHE
    os.environ['XDG_CACHE_HOME'] = CACHE_ROOT
    print("  ✅ Persistence Layer Ready.")

setup_drive()

# ==========================================
# 2. INSTALLATION (Optimized for Colab T4)
# ==========================================
print("\n⏳ Checking Dependencies...")

def install_dependencies():
    marker_file = f"{PIP_CACHE}/installed_v5_t4.marker"

    if os.path.exists(marker_file):
        print("  ✅ Dependencies already installed. Skipping.")
        return

    print("  📦 Installing system dependencies (ffmpeg, nodejs)...")
    subprocess.run("apt-get update -qq && apt-get install -y nodejs ffmpeg",
                    shell=True, capture_output=True, text=True)

    packages = [
        "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git",
        "xformers<0.0.27", "peft", "accelerate", "bitsandbytes",
        "qdrant-client", "sentence-transformers",
        "youtube-transcript-api", "yt-dlp", "faster-whisper",
        "webvtt-py", "nest_asyncio",
        "matplotlib", "scikit-learn", "pandas", "plotly",
    ]

    pkg_str = " ".join([f'"{p}"' for p in packages])
    cmd = f"pip install {pkg_str} --cache-dir {PIP_CACHE} --upgrade-strategy only-if-needed"

    print("  🚀 Running Pip Install (this will take a few minutes)...")
    process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if process.returncode == 0:
        print("  ✅ Python Dependencies Installed/Verified.")
        with open(marker_file, 'w') as f:
            f.write(f"Installed on {time.ctime()} — v5 T4 Optimized")
    else:
        print("  ❌ Dependency Installation had issues.")
        print(process.stderr[-1000:])

install_dependencies()

# ==========================================
# 3. IMPORTS & SETUP
# ==========================================
import torch
import numpy as np

try:
    from huggingface_hub import login
    from google.colab import userdata
    hf_token = userdata.get('HF_TOKEN')
    if hf_token:
        login(token=hf_token)
        print("🔑 Authenticated with HuggingFace.")
    elif 'HF_TOKEN' in os.environ:
        login(token=os.environ['HF_TOKEN'])
except Exception:
    pass

from unsloth import FastLanguageModel
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from faster_whisper import WhisperModel
from youtube_transcript_api import YouTubeTranscriptApi as YTApi
import yt_dlp
import nest_asyncio
nest_asyncio.apply()

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
GPU_NAME = torch.cuda.get_device_name(0) if DEVICE == "cuda" else "CPU"
GPU_VRAM_GB = torch.cuda.get_device_properties(0).total_memory / (1024**3) if DEVICE == "cuda" else 0
print(f"🚀 {DEVICE.upper()} — {GPU_NAME} ({GPU_VRAM_GB:.1f} GB)")


# ==========================================
# CONFIGURATION (T4 SAFE + large-v3 Whisper)
# ==========================================
CONFIG = {
    # Sarvam 2B — fits T4 comfortably. Switch to "sarvamai/sarvam-30b" on A100.
    "sarvam_model": "sarvamai/sarvam-2b-v0.5",
    "max_seq_length": 2048,       # Reduced to save KV cache memory on T4
    "load_in_4bit": True,

    # Embeddings & Reranker
    "embedding_model": "BAAI/bge-base-en-v1.5",
    "reranker_model": "BAAI/bge-reranker-base",

    # Whisper — large-v3 for maximum transcript accuracy
    # Loaded on-demand and freed after use to save VRAM
    "whisper_model": "large-v3",
    "whisper_compute_type": "float16" if DEVICE == "cuda" else "int8",

    # Transcript (10 Indian languages)
    "transcript_languages": ["en", "hi", "te", "ta", "kn", "ml", "bn", "gu", "mr", "pa"],
    "concurrent_workers": 2,      # Conservative for T4 CPU/memory

    # RAG
    "chunk_size": 500,
    "chunk_overlap": 100,
    "qdrant_collection": "mukthi_knowledge_v5",
}


# ==========================================
# VRAM MANAGEMENT HELPERS
# ==========================================

def vram_cleanup():
    """Aggressively free GPU memory."""
    gc.collect()
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

def vram_report(label=""):
    """Print current VRAM usage."""
    if DEVICE == "cuda":
        used = torch.cuda.memory_allocated() / (1024**3)
        free = GPU_VRAM_GB - used
        print(f"  📊 VRAM{' ('+label+')' if label else ''}: {used:.1f}GB used / {GPU_VRAM_GB:.1f}GB total ({free:.1f}GB free)")


# ==========================================
# 4. MODEL LOADING (T4-Safe, On-Demand Whisper)
# ==========================================
model, tokenizer = None, None
embed_model = None
reranker = None
whisper_model_instance = None   # Loaded on-demand, freed after transcription batch

def load_core_models():
    """Load LLM + embeddings. Whisper loaded separately on-demand."""
    global model, tokenizer, embed_model, reranker

    print("\n🧠 Loading Core Models...")

    # A. Sarvam LLM
    if model is None:
        print(f"  🇮🇳 Loading {CONFIG['sarvam_model']} (4-bit)...")
        try:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=CONFIG["sarvam_model"],
                max_seq_length=CONFIG["max_seq_length"],
                dtype=None,
                load_in_4bit=CONFIG["load_in_4bit"],
            )
            FastLanguageModel.for_inference(model)
            vram_report("after LLM")
        except Exception as e:
            print(f"  ❌ LLM failed: {e}")
            print(f"  💡 Try a smaller model or restart runtime.")

    # B. Embeddings & Reranker
    if embed_model is None:
        print("  🧬 Loading BGE Embeddings & Reranker...")
        embed_model = SentenceTransformer(CONFIG["embedding_model"], device=DEVICE)
        reranker = CrossEncoder(CONFIG["reranker_model"], device=DEVICE)

    vram_report("all core models")
    print("  ✅ Core Models Loaded.")

load_core_models()


def load_whisper():
    """Load whisper on-demand (large-v3 eats ~3GB VRAM)."""
    global whisper_model_instance
    if whisper_model_instance is None:
        print(f"  🗣️ Loading faster-whisper {CONFIG['whisper_model']} (on-demand)...")
        whisper_model_instance = WhisperModel(
            CONFIG["whisper_model"],
            device=DEVICE,
            compute_type=CONFIG["whisper_compute_type"],
        )
        vram_report("after whisper load")
    return whisper_model_instance


def unload_whisper():
    """Free whisper from VRAM after transcription is done."""
    global whisper_model_instance
    if whisper_model_instance is not None:
        del whisper_model_instance
        whisper_model_instance = None
        vram_cleanup()
        vram_report("after whisper unload")


# Qdrant Setup
client = QdrantClient(path=QDRANT_PATH)
COLLECTION_NAME = CONFIG["qdrant_collection"]

if not client.collection_exists(COLLECTION_NAME):
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    print(f"  ✅ Created Collection: {COLLECTION_NAME}")
else:
    cnt = client.count(collection_name=COLLECTION_NAME).count
    print(f"  ✅ Connected to Collection: {COLLECTION_NAME} ({cnt} chunks)")


# ==========================================
# 5. 4-TIER TRANSCRIPT EXTRACTION
# ==========================================

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    for p in [r'(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|$)', r'youtu\.be/([0-9A-Za-z_-]{11})',
              r'embed/([0-9A-Za-z_-]{11})', r'shorts/([0-9A-Za-z_-]{11})']:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_transcript_4tier(url):
    """
    4-Tier transcript extraction (robust, T4-safe):
      T1: Manual captions via youtube-transcript-api (10 Indian languages)
      T2: faster-whisper large-v3 transcription (on-demand load/unload)
      T3: yt-dlp subtitle download + VTT/SRT parsing
      T4: Auto-generated captions via youtube-transcript-api
    
    Each tier has retry logic. Whisper is loaded/unloaded on-demand to save VRAM.
    """
    # Get video metadata
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown Video')
            video_id = info['id']
            duration = info.get('duration', 0)
            print(f"   📹 {title} ({duration//60}m{duration%60}s)")
    except Exception as e:
        print(f"   ⚠️ Video info failed: {e}")
        return None, None, "failed"

    languages = CONFIG["transcript_languages"]

    # ── T1: Manual Captions (fastest, most accurate) ──
    print(f"      T1: Manual captions...")
    for attempt in range(2):
        try:
            transcript_list = YTApi.list_transcripts(video_id)
            try:
                manual = transcript_list.find_manually_created_transcript(languages)
                text = " ".join([t['text'] for t in manual.fetch()])
                if text.strip() and len(text.strip()) > 50:
                    print(f"      ✅ T1: {len(text)} chars (manual)")
                    return text.strip(), title, "manual_captions"
            except Exception:
                pass
            break  # API worked but no manual captions found
        except Exception as e:
            if attempt == 0:
                time.sleep(1)  # Brief retry
            else:
                print(f"      T1: API error ({e})")

    # ── T2: faster-whisper large-v3 (on-demand load) ──
    print(f"      T2: faster-whisper large-v3...")
    audio_path = f"/content/temp_{video_id}.mp3"
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_path.replace('.mp3', ''),
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Load whisper on-demand
        wm = load_whisper()
        segments, seg_info = wm.transcribe(
            audio_path,
            beam_size=5,
            language=None,       # Auto-detect
            vad_filter=True,     # Voice Activity Detection for cleaner results
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join([s.text for s in segments])
        detected_lang = getattr(seg_info, 'language', 'unknown')

        # Cleanup audio
        for f in [audio_path, audio_path.replace('.mp3', '')]:
            if os.path.exists(f):
                os.remove(f)

        if text.strip() and len(text.strip()) > 50:
            print(f"      ✅ T2: {len(text)} chars (whisper, lang={detected_lang})")
            return text.strip(), title, "faster_whisper"
    except Exception as e:
        print(f"      ⚠️ T2 failed: {e}")
        for f in [audio_path, audio_path.replace('.mp3', '')]:
            if os.path.exists(f):
                os.remove(f)

    # ── T3: yt-dlp Subtitle Download + VTT/SRT Parse ──
    print(f"      T3: yt-dlp subtitles...")
    try:
        import glob
        with tempfile.TemporaryDirectory() as tmp_dir:
            ydl_opts = {
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': languages,
                'subtitlesformat': 'vtt/srt/best',
                'outtmpl': f"{tmp_dir}/subs",
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            sub_files = glob.glob(f"{tmp_dir}/subs*.vtt") + glob.glob(f"{tmp_dir}/subs*.srt")
            if sub_files:
                text = _parse_subtitle_file(sub_files[0])
                if text and text.strip() and len(text.strip()) > 50:
                    print(f"      ✅ T3: {len(text)} chars (yt-dlp subs)")
                    return text.strip(), title, "ytdlp_subtitles"
    except Exception as e:
        print(f"      ⚠️ T3 failed: {e}")

    # ── T4: Auto-generated Captions ──
    print(f"      T4: Auto captions...")
    for attempt in range(2):
        try:
            transcript_list = YTApi.list_transcripts(video_id)
            auto = transcript_list.find_generated_transcript(languages)
            text = " ".join([t['text'] for t in auto.fetch()])
            if text.strip() and len(text.strip()) > 50:
                print(f"      ✅ T4: {len(text)} chars (auto)")
                return text.strip(), title, "auto_captions"
            break
        except Exception:
            if attempt == 0:
                time.sleep(1)

    print(f"      ❌ All 4 tiers failed for {video_id}")
    return None, title, "failed"


def _parse_subtitle_file(filepath):
    """Parse VTT/SRT subtitle file into clean plaintext (deduped)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    lines = []
    seen = set()
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if re.match(r'^\d{2}:\d{2}', line) or re.match(r'^\d+$', line) or not line:
            continue
        clean = re.sub(r'<[^>]+>', '', line)
        clean = re.sub(r'\{[^}]+\}', '', clean).strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)

    return " ".join(lines)


# ==========================================
# 6. INGESTION (Async, Concurrent, VRAM-Safe)
# ==========================================

def chunk_text(text, size, overlap):
    """Split text into overlapping chunks, skip tiny fragments."""
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return [c for c in chunks if len(c.strip()) > 20]


async def process_video_async(url, semaphore):
    """Async worker for concurrent video processing."""
    async with semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, process_single_video_sync, url)


def process_single_video_sync(url):
    """Sync: 4-tier transcript → chunk → embed → Qdrant. With VRAM cleanup."""
    try:
        print(f"   📥 Processing: {url}")

        # 1. 4-Tier Transcript
        text, title, method = get_transcript_4tier(url)
        if not text:
            print(f"   ⚠️ No transcript for: {url}")
            return {"url": url, "status": "failed", "method": method}

        # 2. Quality Gate
        if len(text) < 100:
            print(f"   ⚠️ Too short ({len(text)} chars), skipping.")
            return {"url": url, "status": "too_short", "method": method}

        # 3. Chunking
        chunks = chunk_text(text, CONFIG["chunk_size"], CONFIG["chunk_overlap"])
        if not chunks:
            return {"url": url, "status": "no_chunks", "method": method}

        # 4. Embed
        embeddings = embed_model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)

        # 5. Upsert to Qdrant
        base_id = time.time_ns()
        points = [
            PointStruct(
                id=base_id + i,
                vector=embeddings[i].tolist(),
                payload={
                    "text": chunks[i],
                    "source": url,
                    "title": title or "Unknown",
                    "method": method,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "timestamp": time.time(),
                }
            )
            for i in range(len(chunks))
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"   ✅ {(title or '?')[:40]}... ({len(chunks)} chunks, {method})")

        # VRAM cleanup after embedding
        del embeddings
        vram_cleanup()

        return {"url": url, "status": "success", "title": title, "method": method, "chunks": len(chunks)}

    except Exception as e:
        print(f"   ❌ Error {url}: {e}")
        vram_cleanup()
        return {"url": url, "status": "error", "error": str(e)}


async def _ingest_concurrent(url):
    """Ingest playlist/channel/video with concurrent workers."""
    print(f"\n📂 Analyzing: {url}")
    ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)
        if 'entries' not in result:
            # Single video
            return [process_single_video_sync(url)]

        videos = [e for e in result['entries'] if e and e.get('id')]
        workers = CONFIG["concurrent_workers"]
        print(f"   Found {len(videos)} videos → {workers} concurrent workers")

        sem = asyncio.Semaphore(workers)
        tasks = [
            process_video_async(f"https://www.youtube.com/watch?v={v['id']}", sem)
            for v in videos
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        final = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final.append({"url": videos[i].get('url', ''), "status": "exception", "error": str(r)})
            else:
                final.append(r)

        # Unload whisper after batch to reclaim VRAM
        unload_whisper()

        # Summary
        success = sum(1 for r in final if r.get("status") == "success")
        failed = len(final) - success
        total_chunks = sum(r.get("chunks", 0) for r in final if r.get("status") == "success")
        methods = {}
        for r in final:
            m = r.get("method", "?")
            methods[m] = methods.get(m, 0) + 1

        print(f"\n{'='*50}")
        print(f"📊 Ingestion Summary:")
        print(f"   ✅ Success: {success}/{len(final)}")
        print(f"   ❌ Failed:  {failed}/{len(final)}")
        print(f"   📦 Chunks indexed: {total_chunks}")
        print(f"   🔧 Methods: {methods}")
        vram_report("post-ingestion")

        return final


def ingest_url(url):
    """Synchronous entry point for ingestion."""
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(_ingest_concurrent(url))
    # Unload whisper after ingestion to free VRAM for chat
    unload_whisper()
    return results


def batch_ingest(urls):
    """Ingest multiple URLs in sequence."""
    print(f"\n📦 Batch Ingestion: {len(urls)} URLs")
    all_results = []
    for i, url in enumerate(urls):
        print(f"\n{'='*50}")
        print(f"[{i+1}/{len(urls)}] {url}")
        results = ingest_url(url)
        all_results.extend(results if isinstance(results, list) else [results])

    success = sum(1 for r in all_results if r.get("status") == "success")
    print(f"\n🏁 Batch Complete: {success}/{len(all_results)} videos indexed")
    return all_results


# ==========================================
# 7. ENHANCED RAG (VRAM-Safe)
# ==========================================

def get_guru_response(question, verbose=False):
    """
    Full RAG with VRAM management:
    HyDE expansion → retrieval → reranking → Sarvam generation → VRAM cleanup.
    Responds in the user's language.
    """
    if model is None or tokenizer is None:
        return "❌ LLM not loaded. Check model loading logs."

    if verbose:
        print(f"\n🤔 Question: {question}")

    # 1. HyDE — Hypothetical answer for better retrieval
    system_prompt = "You are a spiritual master fluent in Indian languages. Write a 1-sentence hypothetical answer based on Mukthi philosophy."
    hyde_prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n{question}<|eot_id|><|start_header_id|>assistant<|end_header_id|>"

    inputs = tokenizer([hyde_prompt], return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=50, use_cache=True)
    hypothetical = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    del inputs, outputs
    vram_cleanup()

    if verbose:
        print(f"   💭 HyDE: {hypothetical[:80]}...")

    # 2. Retrieval with query expansion
    search_query = f"{question} {hypothetical}"
    q_vec = embed_model.encode(search_query, normalize_embeddings=True)

    search_result = client.query_points(collection_name=COLLECTION_NAME, query=q_vec, limit=15)
    docs = [point.payload for point in search_result.points]

    if not docs:
        return "🕉️ I have no knowledge on this yet. Please ingest content first."

    # 3. Reranking (CrossEncoder precision layer)
    pairs = [[question, doc["text"]] for doc in docs]
    scores = reranker.predict(pairs)

    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    top_docs = [(doc, score) for doc, score in ranked if score > -2.5][:3]

    if verbose:
        print(f"   🔍 {len(docs)} → Reranked to {len(top_docs)} docs")
        for i, (doc, score) in enumerate(top_docs):
            print(f"      [{i+1}] {score:.2f} | {doc['text'][:60]}...")

    context_text = "\n\n".join([f"[{d.get('title', '')[:30]}]\n{d['text']}" for d, _ in top_docs])

    # 4. Generate with Sarvam (multilingual)
    final_prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are AskMukthiGuru, a deeply compassionate spiritual guide fluent in all Indian languages.
- Answer based ONLY on the context below
- Match the user's language (Hindi→Hindi, Telugu→Telugu, etc.)
- Be warm, wise, and specific
- If context doesn't cover it, say so honestly

Context:
{context_text}
<|eot_id|><|start_header_id|>user<|end_header_id|>
{question}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>"""

    inputs = tokenizer([final_prompt], return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=300,
            temperature=0.3,
            repetition_penalty=1.15,
            use_cache=True,
        )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    # VRAM cleanup after generation
    del inputs, outputs
    vram_cleanup()

    return response


# ==========================================
# 8. UTILITIES
# ==========================================

def show_stats():
    """System stats + knowledge base overview."""
    cnt = client.count(collection_name=COLLECTION_NAME).count
    print(f"\n{'='*50}")
    print(f"📊 MUKTHI GURU v5.0 — System Stats")
    print(f"{'='*50}")
    vram_report()
    print(f"   🧠 LLM: {CONFIG['sarvam_model']} (4-bit)")
    print(f"   🗣️ Whisper: faster-whisper {CONFIG['whisper_model']} (on-demand)")
    print(f"   🧬 Embeddings: {CONFIG['embedding_model']}")
    print(f"   📚 Knowledge: {cnt} chunks")
    print(f"   🌐 Languages: {', '.join(CONFIG['transcript_languages'])}")
    print(f"   ⚡ Workers: {CONFIG['concurrent_workers']}")

    if cnt > 0:
        try:
            pts = client.scroll(COLLECTION_NAME, limit=500, with_payload=True, with_vectors=False)[0]
            sources, methods = {}, {}
            for p in pts:
                s = p.payload.get("title", "Unknown")
                m = p.payload.get("method", "Unknown")
                sources[s] = sources.get(s, 0) + 1
                methods[m] = methods.get(m, 0) + 1

            print(f"\n   📋 Sources ({len(sources)} videos):")
            for s, c in sorted(sources.items(), key=lambda x: -x[1])[:10]:
                print(f"      • {s[:50]}: {c} chunks")
            print(f"   🔧 Methods:")
            for m, c in sorted(methods.items(), key=lambda x: -x[1]):
                print(f"      • {m}: {c}")
        except Exception:
            pass


def search_knowledge(query, top_k=5):
    """Semantic search without LLM — useful for debugging."""
    q_vec = embed_model.encode(query, normalize_embeddings=True)
    results = client.query_points(collection_name=COLLECTION_NAME, query=q_vec, limit=top_k)
    print(f"\n🔍 '{query}' → {len(results.points)} results")
    for i, p in enumerate(results.points):
        print(f"   [{i+1}] {p.score:.4f} | {p.payload.get('title', '?')[:40]} | {p.payload['text'][:100]}...")
    return results


def clear_knowledge():
    """Clear all indexed knowledge (with confirmation)."""
    cnt = client.count(collection_name=COLLECTION_NAME).count
    confirm = input(f"⚠️ Delete all {cnt} chunks? Type 'YES': ")
    if confirm == 'YES':
        client.delete_collection(COLLECTION_NAME)
        client.create_collection(
            COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print("✅ Knowledge base cleared.")
    else:
        print("❌ Cancelled.")


# ==========================================
# 9. MAIN INTERFACE
# ==========================================
def main_menu():
    print(f"\n{'='*50}")
    print(f"🕉️ MUKTHI GURU v5.0 — {CONFIG['sarvam_model']} | {GPU_NAME}")
    print(f"{'='*50}")

    while True:
        print(f"\n 1. Ingest (Video/Playlist/Channel)")
        print(f" 2. Batch Ingest (Multiple URLs)")
        print(f" 3. Ask Guru (RAG Chat)")
        print(f" 4. Search Knowledge Base")
        print(f" 5. System Stats")
        print(f" 6. Clear Knowledge Base")
        print(f" 7. Exit")

        c = input("→ ").strip()
        if c == '1':
            url = input("URL: ").strip()
            if url:
                ingest_url(url)
        elif c == '2':
            print("Enter URLs (one per line, empty to finish):")
            urls = []
            while True:
                u = input("  URL: ").strip()
                if not u: break
                urls.append(u)
            if urls:
                batch_ingest(urls)
        elif c == '3':
            q = input("Question (any language): ").strip()
            if q:
                response = get_guru_response(q, verbose=True)
                print(f"\n🕉️ {response}")
        elif c == '4':
            q = input("Search: ").strip()
            if q:
                search_knowledge(q)
        elif c == '5':
            show_stats()
        elif c == '6':
            clear_knowledge()
        elif c == '7':
            print("🙏 Namaste!")
            break


print("\n🕉️ Mukthi Guru v5.0 Ready!")
print("   ingest_url('URL')              — ingest video/playlist/channel")
print("   batch_ingest(['URL1','URL2'])   — batch ingest")
print("   get_guru_response('question')   — ask anything (any language)")
print("   search_knowledge('query')       — search knowledge base")
print("   show_stats()                    — system stats")
print("   main_menu()                     — interactive mode")
