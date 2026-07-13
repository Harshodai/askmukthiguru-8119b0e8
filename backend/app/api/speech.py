"""Speech-to-text, text-to-speech, and translation routes."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase
from services.sarvam_service import SarvamCloudService
from services.whisper_local_service import transcribe_with_whisper

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Speech"])


class SpeechTTSRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    target_language_code: str
    speaker: Optional[str] = None


@router.post("/speech/stt")
@limiter.limit("10/minute")
async def speech_to_text_endpoint(
    request: Request,
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    model: str = Form("saaras:v3"),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """
    Transcribe uploaded audio file using Sarvam Cloud STT or fallback to local Whisper.
    """
    MAX_AUDIO_BYTES = 25 * 1024 * 1024
    ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/wav", "audio/wave", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/x-m4a", "audio/mp4"}

    if file.size and file.size > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large. Maximum size is 25MB.")
    if not file.content_type or file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported audio format. Supported: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}")

    content = await file.read(MAX_AUDIO_BYTES + 1)
    if len(content) > MAX_AUDIO_BYTES or not content:
        raise HTTPException(status_code=413, detail="Audio file too large. Maximum size is 25MB.")

    api_key = settings.sarvam_api_key

    if api_key and not api_key.startswith("sk_dummy") and len(api_key) > 10:
        try:
            logger.info("Calling Sarvam STT Cloud API...")
            headers = {
                "api-subscription-key": api_key,
            }
            files = {
                "file": (file.filename or "audio.webm", content, file.content_type or "audio/webm")
            }
            data = {"model": model}
            if language_code:
                data["language_code"] = language_code

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.sarvam.ai/speech-to-text", headers=headers, files=files, data=data
                )
                if resp.status_code == 200:
                    result = resp.json()
                    transcript = result.get("transcript", "")
                    detected_lang = result.get("language_code", language_code or "en-IN")
                    logger.info(
                        f"Sarvam STT returned transcript: {transcript} (lang: {detected_lang})"
                    )
                    return {"transcript": transcript, "language_code": detected_lang}
                else:
                    logger.error(f"Sarvam STT failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error calling Sarvam STT: {e}")

    # Fallback to local Whisper
    try:
        logger.info("Falling back to local Whisper STT...")
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            whisper_lang = "en"
            if language_code:
                whisper_lang = language_code.split("-")[0].lower()

            transcript = transcribe_with_whisper(
                video_id="browser_recording", audio_path=tmp_path, language=whisper_lang
            )

            if transcript:
                detected_lang = language_code or "en-IN"
                if any("ऀ" <= c <= "ॿ" for c in transcript):
                    detected_lang = "hi-IN"
                elif any("ఀ" <= c <= "౿" for c in transcript):
                    detected_lang = "te-IN"
                elif any("஀" <= c <= "௿" for c in transcript):
                    detected_lang = "ta-IN"

                return {"transcript": transcript, "language_code": detected_lang}
            else:
                raise Exception("Whisper returned empty transcript")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        logger.error(f"Local Whisper fallback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Speech transcription failed. Please try again.")


@router.post("/speech/tts")
@limiter.limit("10/minute")
async def text_to_speech_endpoint(
    request: Request,
    req: SpeechTTSRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """
    Generate speech from text using Sarvam Cloud TTS.
    """
    api_key = settings.sarvam_api_key
    if not api_key or api_key.startswith("sk_dummy") or len(api_key) <= 10:
        raise HTTPException(
            status_code=500, detail="Speech synthesis is not available at this time."
        )

    lang = req.target_language_code
    if "-" not in lang:
        mapping = {
            "en": "en-IN",
            "hi": "hi-IN",
            "bn": "bn-IN",
            "te": "te-IN",
            "mr": "mr-IN",
            "ta": "ta-IN",
            "ur": "ur-IN",
            "gu": "gu-IN",
            "kn": "kn-IN",
            "ml": "ml-IN",
            "or": "or-IN",
            "pa": "pa-IN",
            "as": "as-IN",
            "mai": "mai-IN",
            "sa": "sa-IN",
            "ks": "ks-IN",
            "ne": "ne-NP",
            "sd": "sd-IN",
            "kok": "kok-IN",
            "doi": "doi-IN",
            "mni": "mni-IN",
            "sat": "sat-IN",
            "brx": "brx-IN",
        }
        lang = mapping.get(lang.lower(), f"{lang.lower()}-IN")

    speaker = req.speaker or "shubh"

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    payload = {
        "inputs": [req.text],
        "target_language_code": lang,
        "speaker": speaker,
        "model": "bulbul:v3",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                audios = data.get("audios", [])
                if audios:
                    return {"audio": audios[0]}
                else:
                    raise Exception("Sarvam TTS returned empty audio list")
            else:
                logger.error(f"Sarvam TTS failed with status {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=502, detail="Speech synthesis failed. Please try again."
                )
    except Exception as e:
        logger.error(f"Error calling Sarvam TTS: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Speech synthesis failed. Please try again.")


class TranslateRequest(BaseModel):
    text: str = Field(..., max_length=10000)
    source_language_code: str = Field(default="en-IN")
    target_language_code: str = Field(..., min_length=2, max_length=10)


@router.post("/translate")
@limiter.limit("30/minute")
async def translate_endpoint(
    request: Request,
    req: TranslateRequest,
    user: dict = Depends(get_current_user_from_supabase),
):
    api_key = settings.sarvam_api_key
    if not api_key or api_key.startswith("sk_dummy") or len(api_key) <= 10:
        raise HTTPException(
            status_code=500, detail="Translation service is not available at this time."
        )

    service = SarvamCloudService()
    translated = await service.translate_text(
        text=req.text,
        source_language_code=req.source_language_code,
        target_language_code=req.target_language_code,
    )
    return {"translated_text": translated, "source": req.source_language_code, "target": req.target_language_code}
