"""Speech-to-text, text-to-speech, and translation routes."""

from __future__ import annotations

import base64
import hashlib
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
from app.language_utils import detect_message_lang
from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    ArtifactModality,
    EUComplianceRiskTier,
    OriginType,
    SoftwareAgentDescriptor,
)
from services.auth_service import get_current_user_from_supabase
from services.sarvam_service import SarvamCloudService
from services.watermarking_service import WatermarkingService
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
    ALLOWED_AUDIO_TYPES = {
        "audio/webm",
        "audio/wav",
        "audio/wave",
        "audio/mp3",
        "audio/mpeg",
        "audio/ogg",
        "audio/x-m4a",
        "audio/mp4",
    }

    # P1-BE-8: the cap MUST be enforced before any decode/transcribe work.
    # Order matters here:
    #   1. declared size check (fast reject, no body read)
    #   2. content-type check
    #   3. bounded read of MAX_AUDIO_BYTES + 1 bytes
    #   4. post-read size check -> 413
    #   5. only then hand bytes to Sarvam/Whisper
    # If the read happened first, a hostile 30MB upload would be fully
    # buffered into memory before being rejected — the very DoS this cap
    # exists to prevent.
    if file.size and file.size > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large. Maximum size is 25MB.")
    base_type = (file.content_type or "").split(";")[0].strip()
    if not base_type or base_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format. Supported: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}",
        )

    content = await file.read(MAX_AUDIO_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="No audio content provided.")
    if len(content) > MAX_AUDIO_BYTES:
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
                msg_lang = detect_message_lang(transcript)
                if msg_lang and msg_lang not in ("en", "non_en"):
                    # Sarvam's canonical Odia tag is "od-IN", not "or-IN" —
                    # detect_message_lang uses ISO 639-1 "or" for Oriya script.
                    detected_lang = "od-IN" if msg_lang == "or" else f"{msg_lang}-IN"

                return {"transcript": transcript, "language_code": detected_lang}
            else:
                raise Exception("Whisper returned empty transcript")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        logger.error(f"Local Whisper fallback failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Speech transcription failed. Please try again."
        )


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
                    raw_audio_b64 = audios[0]
                    raw_audio_bytes = base64.b64decode(raw_audio_b64)

                    user_id = user.get("id") if user else None
                    user_id_hash = (
                        f"sha256:{hashlib.sha256(str(user_id).encode('utf-8')).hexdigest()}"
                        if user_id
                        else None
                    )

                    manifest = AIProvenanceManifest(
                        modality=ArtifactModality.SYNTHETIC_AUDIO,
                        origin_type=OriginType.AI_GENERATED,
                        risk_tier=EUComplianceRiskTier.TRANSPARENCY_ART50,
                        agent=SoftwareAgentDescriptor(
                            agent_id="sarvam-bulbul-v3",
                            name="Sarvam Bulbul TTS",
                            version="3.0",
                            model_name="bulbul:v3",
                            provider="sarvam",
                            role="Synthetic Audio Synthesizer",
                        ),
                        content_hash=f"sha256:{hashlib.sha256(raw_audio_bytes).hexdigest()}",
                        disclosure_statement=(
                            "This audio was synthetically generated by AskMukthiGuru AI assistant "
                            "using Sarvam Bulbul TTS in accordance with EU AI Act Article 50."
                        ),
                        user_id_hash=user_id_hash,
                        metadata={
                            "language_code": lang,
                            "speaker": speaker,
                            "text_preview": req.text[:100],
                        },
                    )

                    tagged_audio_bytes = WatermarkingService.inject_audio_provenance(
                        audio_bytes=raw_audio_bytes,
                        manifest=manifest,
                        format="mp3",
                    )
                    tagged_b64 = base64.b64encode(tagged_audio_bytes).decode("ascii")

                    # Try to record provenance in ontology graph asynchronously/non-blocking
                    try:
                        from services.provenance_ontology_service import (
                            get_provenance_ontology_service,
                        )

                        prov_service = get_provenance_ontology_service(
                            neo4j_driver=getattr(container, "neo4j_driver", None)
                        )
                        prov_service.record_provenance(manifest=manifest)
                    except Exception as p_err:
                        logger.debug("Failed to record audio provenance in ontology: %s", p_err)

                    return {
                        "audio": tagged_b64,
                        "provenance": manifest.model_dump(),
                    }
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
    return {
        "translated_text": translated,
        "source": req.source_language_code,
        "target": req.target_language_code,
    }
