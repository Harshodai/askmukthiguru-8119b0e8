"""
Mukthi Guru — OCR Service

Design Patterns:
  - Adapter Pattern: Wraps EasyOCR behind a simple interface
  - Lazy Loading: EasyOCR reader initialized on first call (heavy model)
  - Strategy Pattern: URL vs file path input handling
  - Thread-safe: Reader initialization uses a lock

Supports: English, Hindi, Telugu (configurable via OCR_LANGUAGES env var)
Runs on CPU to leave GPU free for the LLM.
"""

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """
    Extract text from images using EasyOCR.
    
    Lazy-loaded: The EasyOCR reader (~200MB) is only loaded when
    the first OCR request comes in. This saves memory if OCR is never used.
    
    Thread-safe: Uses a lock around reader initialization to prevent
    double-loading in concurrent request scenarios.
    """

    def __init__(self) -> None:
        """Initialize with None reader — will be loaded on first use."""
        self._reader = None
        self._reader_lock = threading.Lock()
        self._languages = settings.ocr_languages_list
        logger.info(f"OCR service initialized (lazy load). Languages: {self._languages}")

    def _ensure_reader(self) -> None:
        """
        Lazy-load the EasyOCR reader on first use.
        
        Thread-safe: Double-checked locking ensures only one reader is created
        even if multiple threads call this concurrently.
        """
        if self._reader is not None:
            return
        with self._reader_lock:
            if self._reader is None:
                import easyocr
                logger.info(f"Loading EasyOCR reader for: {self._languages}")
                self._reader = easyocr.Reader(
                    self._languages,
                    gpu=False,  # CPU only — GPU reserved for LLM
                )
                logger.info("EasyOCR reader loaded")

    def extract_text_from_url(self, image_url: str) -> dict:
        """
        Download an image from URL and extract text via OCR.
        
        Args:
            image_url: HTTP(S) URL to an image (JPG, PNG, WEBP)
            
        Returns:
            Dict with 'text', 'source_url', 'content_type', 'confidence'
        """
        logger.info(f"OCR: downloading {image_url}")
        tmp_path = None

        try:
            response = requests.get(image_url, timeout=30, stream=True)
            response.raise_for_status()

            # Validate content type
            content_type = response.headers.get("content-type", "")
            if not any(t in content_type for t in ["image/", "application/octet-stream"]):
                raise ValueError(f"URL does not point to an image: {content_type}")

            # Save to temp file for EasyOCR
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

            return self._extract_from_file(tmp_path, source_url=image_url)

        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to download/validate image: {e}")
            return {
                "text": "",
                "source_url": image_url,
                "content_type": "image",
                "confidence": 0.0,
                "error": str(e),
            }
        finally:
            # Clean up temp file regardless of success/failure
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def extract_text_from_file(self, file_path: str) -> dict:
        """
        Extract text from a local image file.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Dict with 'text', 'source_url', 'content_type', 'confidence'
        """
        return self._extract_from_file(file_path, source_url=f"file://{file_path}")

    def _extract_from_file(self, file_path: str, source_url: str = "") -> dict:
        """
        Internal: Run EasyOCR on a file path.
        
        Returns structured result with text and confidence score.
        """
        self._ensure_reader()

        try:
            results = self._reader.readtext(file_path, detail=1)

            # results = [(bbox, text, confidence), ...]
            texts = []
            confidences = []
            for _bbox, text, conf in results:
                if text.strip():
                    texts.append(text.strip())
                    confidences.append(conf)

            combined_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            logger.info(
                f"OCR extracted {len(texts)} text segments, "
                f"avg confidence: {avg_confidence:.2f}"
            )

            return {
                "text": combined_text,
                "source_url": source_url,
                "content_type": "image",
                "confidence": avg_confidence,
            }

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return {
                "text": "",
                "source_url": source_url,
                "content_type": "image",
                "confidence": 0.0,
                "error": str(e),
            }

    def health_check(self) -> bool:
        """Check if EasyOCR can be imported (don't load the model for health check)."""
        try:
            import easyocr
            return True
        except ImportError:
            return False
