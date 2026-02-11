"""
Mukthi Guru — Image Content Loader

Design Patterns:
  - Facade Pattern: Simple interface over OCR service
  - Adapter Pattern: Normalizes image input (URL or file) into text

Routes image URLs through the OCR service and returns structured results
ready for the ingestion pipeline.
"""

import logging
import re
from typing import Optional

from services.ocr_service import OCRService

logger = logging.getLogger(__name__)

# Regex patterns for image URL detection
IMAGE_EXTENSIONS = re.compile(
    r'\.(jpg|jpeg|png|webp|gif|bmp|tiff|svg)(\?.*)?$',
    re.IGNORECASE,
)


def is_image_url(url: str) -> bool:
    """Check if a URL points to an image based on extension or content-type hint."""
    return bool(IMAGE_EXTENSIONS.search(url))


def process_image_url(url: str, ocr_service: Optional[OCRService] = None) -> dict:
    """
    Download an image URL and extract text via OCR.
    
    Args:
        url: HTTP(S) URL to an image
        ocr_service: Optional pre-initialized OCR service (for DI)
        
    Returns:
        Dict with 'text', 'source_url', 'title', 'content_type', 'method'
    """
    if ocr_service is None:
        ocr_service = OCRService()

    result = ocr_service.extract_text_from_url(url)

    if result.get("error"):
        logger.warning(f"Image OCR failed for {url}: {result['error']}")

    return {
        "text": result.get("text", ""),
        "source_url": url,
        "title": f"Image: {url.split('/')[-1].split('?')[0]}",
        "content_type": "image",
        "method": "easyocr",
        "confidence": result.get("confidence", 0.0),
    }
