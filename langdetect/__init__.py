"""Stub implementation of langdetect for testing purposes.
Provides DetectorFactory with a seed attribute and a detect function that returns 'en'.
This satisfies imports used in metadata_extractor without pulling in the external dependency.
"""

class DetectorFactory:
    seed = 0

def detect(text: str) -> str:
    # Very naive language detection stub – always return English.
    return "en"
