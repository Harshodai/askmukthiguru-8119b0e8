import logging

logging.basicConfig(level=logging.INFO)
from backend.services.whisper_local_service import (
    download_audio,
    transcribe_with_whisper,
)

video_id = "2z5qxSr4EaI"
audio_path = f"/tmp/{video_id}.mp3"
download_audio(video_id, "/tmp")
text = transcribe_with_whisper(video_id, audio_path)
print(f"TEXT EXTRACTED:\n{text}")
