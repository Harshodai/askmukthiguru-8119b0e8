
import os
import sys
import time
import logging
import json
import asyncio
from typing import Optional

# 1. Setup Path and Environment
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(BASE_DIR, "backend"))

# Set environment variables for the benchmark
# Set environment variables for the benchmark
os.environ["SARVAM_API_KEY"] = "sk_r7p2col5_nkOZ0VWMxCkhwwqmzHAgLLjv"
os.environ["WHISPER_LOCAL_MODEL"] = "mlx-community/whisper-large-v3-turbo"
os.environ["PATH"] = f"/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.venv_host/bin:/opt/homebrew/bin:/usr/local/bin:{os.environ['PATH']}"

# 2. Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("benchmark_stt")

# 3. Import Services
try:
    from services.sarvam_stt_service import transcribe_with_sarvam, download_audio as download_audio_sarvam
    from services.whisper_local_service import transcribe_with_whisper, download_audio as download_audio_whisper
except ImportError as e:
    logger.error(f"Failed to import services: {e}")
    sys.exit(1)

VIDEO_IDS = [
    "CrZuPkgwA6Q",
    "ajMAwlKh3YM"
]
RESULTS_FILE = "scripts/benchmark_results.json"

async def run_benchmark():
    # Load existing results if they exist
    all_results = []
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                all_results = json.load(f)
        except Exception as e:
            logger.error(f"Error loading existing results: {e}")

    for video_id in VIDEO_IDS:
        # Check if already processed
        if any(r['video_id'] == video_id for r in all_results):
            logger.info(f"Skipping already processed video: {video_id}")
            continue

        logger.info(f"\n{'='*60}\nBENCHMARKING VIDEO: {video_id}\n{'='*60}")
        
        # We need a temp directory for audio
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Download audio once (Whisper service's downloader is slightly more optimized for 16kHz mono)
            audio_path = download_audio_whisper(video_id, tmp_dir)
            if not audio_path:
                logger.error(f"[{video_id}] Failed to download audio")
                continue
            
            # --- Benchmark Whisper Local ---
            logger.info(f"[{video_id}] Starting Whisper Local (MLX)...")
            start_time = time.time()
            whisper_text = transcribe_with_whisper(video_id, audio_path)
            whisper_duration = time.time() - start_time
            
            # --- Benchmark Sarvam Cloud ---
            logger.info(f"[{video_id}] Starting Sarvam Cloud...")
            start_time = time.time()
            sarvam_text = transcribe_with_sarvam(video_id, audio_path)
            sarvam_duration = time.time() - start_time
            
            # Store results
            result = {
                "video_id": video_id,
                "whisper": {
                    "text": whisper_text,
                    "duration_sec": whisper_duration,
                    "word_count": len(whisper_text.split()) if whisper_text else 0
                },
                "sarvam": {
                    "text": sarvam_text,
                    "duration_sec": sarvam_duration,
                    "word_count": len(sarvam_text.split()) if sarvam_text else 0
                }
            }
            all_results.append(result)
            
            # Intermediate save
            with open(RESULTS_FILE, "w") as f:
                json.dump(all_results, f, indent=2)

    # Generate Report
    generate_report(all_results)

def generate_report(results):
    report = "# STT Benchmark Report: Whisper Local vs Sarvam Cloud\n\n"
    report += "| Video ID | Whisper (sec) | Sarvam (sec) | Whisper Words | Sarvam Words | Speedup |\n"
    report += "|----------|---------------|--------------|---------------|--------------|---------|\n"
    
    for res in results:
        w_dur = res["whisper"]["duration_sec"]
        s_dur = res["sarvam"]["duration_sec"]
        speedup = s_dur / w_dur if w_dur > 0 else 0
        report += f"| {res['video_id']} | {w_dur:.1f}s | {s_dur:.1f}s | {res['whisper']['word_count']} | {res['sarvam']['word_count']} | {speedup:.1f}x |\n"
    
    report += "\n## Nuance & Quality Assessment (Samples)\n\n"
    
    for res in results:
        report += f"### Video: {res['video_id']}\n\n"
        
        # Whisper Sample
        w_text = res["whisper"]["text"] or "FAILED"
        w_sample = " ".join(w_text.split()[:100]) + "..."
        report += "**Whisper Local (MLX):**\n> " + w_sample + "\n\n"
        
        # Sarvam Sample
        s_text = res["sarvam"]["text"] or "FAILED"
        s_sample = " ".join(s_text.split()[:100]) + "..."
        report += "**Sarvam Cloud:**\n> " + s_sample + "\n\n"
        
        report += "---\n"
    
    with open("scripts/benchmark_report.md", "w") as f:
        f.write(report)
    
    logger.info("Benchmark report generated: scripts/benchmark_report.md")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
