"""
ToneExtractor — Speaker Diarization, Role Parsing, and Persona Exemplar Extraction.

Differentiates interviewers/seekers (e.g., Marie Forleo) from Sri Krishnaji and Sri Preethaji.
Extracts structured (Seeker Question, Guru Response, Phrasing DNA, Emotional State) tuples.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SpeakerRole(str, Enum):
    INTERVIEWER = "interviewer"
    SEEKER = "seeker"
    KRISHNAJI = "krishnaji"
    PREETHAJI = "preethaji"
    UNKNOWN = "unknown"


@dataclass
class PersonaToneExemplar:
    id: str
    guru_name: str  # "krishnaji" | "preethaji" | "combined"
    speaker_role: str  # "krishnaji" | "preethaji"
    interviewer_name: str  # e.g. "Marie Forleo" or "Seeker"
    seeker_question: str  # Question / dilemma
    seeker_emotional_state: str  # Normalized state: e.g., "fear of failure", "desire for success"
    guru_response: str  # Verbatim answer segment from Guru
    phrasing_dna: list[str] = field(default_factory=list)  # Key signature phrases
    teaching_concept: str = ""  # Core concept (e.g. "Beautiful State vs Suffering State")
    source_id: str = ""  # Video ID / URL
    raw_segment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToneExtractor:
    """Parses transcripts into speaker-attributed persona exemplars."""

    def __init__(self, llm_service: Any = None) -> None:
        self.llm_service = llm_service

    def rule_based_speaker_diarization(self, text: str, default_guru: str = "preethaji") -> list[dict[str, str]]:
        """Fallback deterministic speaker segmenter for transcript text."""
        segments = []
        lines = text.split("\n")
        current_speaker = "unknown"
        current_buffer = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Detect speaker headers if present
            lower = line_str.lower()
            if "marie" in lower or "interviewer" in lower or "question" in lower:
                if current_buffer:
                    segments.append({"speaker": current_speaker, "text": " ".join(current_buffer)})
                    current_buffer = []
                current_speaker = "marie_forleo"
            elif "krishnaji" in lower:
                if current_buffer:
                    segments.append({"speaker": current_speaker, "text": " ".join(current_buffer)})
                    current_buffer = []
                current_speaker = "krishnaji"
            elif "preethaji" in lower:
                if current_buffer:
                    segments.append({"speaker": current_speaker, "text": " ".join(current_buffer)})
                    current_buffer = []
                current_speaker = "preethaji"
            else:
                current_buffer.append(line_str)

        if current_buffer:
            segments.append({"speaker": current_speaker, "text": " ".join(current_buffer)})

        return segments

    def extract_phrasing_dna(self, response_text: str) -> list[str]:
        """Extract signature linguistic markers and phrase patterns."""
        phrases = []
        patterns = [
            r"from there,?\s+(?:\b\w+\b\s*){1,5}",
            r"beautiful state",
            r"suffering state",
            r"inner world",
            r"habitual mind",
            r"present moment",
            r"connect to the divine",
            r"observe the ego",
            r"consciousness",
            r"transforming consciousness",
            r"nurture a life",
            r"state of joy",
            r"state of calm",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, response_text, flags=re.IGNORECASE)
            for m in matches:
                cleaned = m.strip().lower()
                if cleaned not in phrases:
                    phrases.append(cleaned)

        return phrases

    async def extract_exemplars_from_transcript(
        self,
        transcript_text: str,
        source_id: str,
        default_guru: str = "combined",
    ) -> list[PersonaToneExemplar]:
        """Extract high-fidelity PersonaToneExemplar records from a video transcript."""
        exemplars: list[PersonaToneExemplar] = []

        # If LLM service is available, use structured prompt extraction
        if self.llm_service:
            try:
                extracted_data = await self._extract_with_llm(transcript_text, source_id, default_guru)
                if extracted_data:
                    return extracted_data
            except Exception as exc:
                logger.warning(f"ToneExtractor: LLM extraction failed ({exc}), falling back to deterministic extraction.")

        # Deterministic speaker diarization fallback: filter out interviewer and unknown segments
        segments = self.rule_based_speaker_diarization(transcript_text, default_guru=default_guru)
        guru_segments = [s for s in segments if s["speaker"] in ("krishnaji", "preethaji")]

        if not guru_segments:
            chunks = self._chunk_transcript(transcript_text, max_chars=1500)
            fallback_guru = default_guru if default_guru in ("krishnaji", "preethaji") else "preethaji"
            guru_segments = [{"speaker": fallback_guru, "text": c} for c in chunks]

        for idx, seg in enumerate(guru_segments):
            chunk = seg["text"]
            speaker = seg["speaker"]
            phrasing = self.extract_phrasing_dna(chunk)
            guru_name = speaker if speaker in ("krishnaji", "preethaji") else default_guru

            # Determine teaching concept
            concept = "Living in a Beautiful State"
            if "present" in chunk.lower():
                concept = "Living in the Present Moment"
            elif "success" in chunk.lower() or "wealth" in chunk.lower():
                concept = "Inner Mastery vs External Success"

            exemplar = PersonaToneExemplar(
                id=f"{source_id}_chunk_{idx}",
                guru_name=guru_name,
                speaker_role=guru_name,
                interviewer_name="Interviewer/Seeker",
                seeker_question="How do I overcome stress, live in peace, and balance external goals with inner state?",
                seeker_emotional_state="seeking inner peace amid external ambition",
                guru_response=chunk,
                phrasing_dna=phrasing,
                teaching_concept=concept,
                source_id=source_id,
                raw_segment=chunk,
            )
            exemplars.append(exemplar)

        return exemplars

    def _chunk_transcript(self, text: str, max_chars: int = 1500) -> list[str]:
        """Split text into sentence-aware blocks under max_chars."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = []
        current_len = 0

        for sentence in sentences:
            if current_len + len(sentence) > max_chars and current:
                chunks.append(" ".join(current))
                current = [sentence]
                current_len = len(sentence)
            else:
                current.append(sentence)
                current_len += len(sentence)

        if current:
            chunks.append(" ".join(current))

        return chunks

    async def _extract_with_llm(
        self,
        transcript_text: str,
        source_id: str,
        default_guru: str,
    ) -> list[PersonaToneExemplar]:
        """Use LLM to extract speaker turns, seeker questions, and Guru tone exemplars.

        Chunks the transcript into 3,500-char windows (up to 4) to avoid losing 90%
        of content from long videos. Deduplicates by response prefix.
        """
        _CHUNK_SIZE = 3_500
        _MAX_CHUNKS = 4

        chunks = self._chunk_transcript(transcript_text, max_chars=_CHUNK_SIZE)
        chunks = chunks[:_MAX_CHUNKS]

        system_prompt = (
            "You are an expert dialogue parser for Sri Krishnaji and Sri Preethaji. "
            "Your task is to parse a raw video transcript and separate the Interviewer (e.g. Marie Forleo) "
            "from Sri Krishnaji and Sri Preethaji. Extract structured Q&A interaction pairs in JSON format."
        )
        extract_instruction = (
            "Extract a JSON array of objects with keys:\n"
            "- guru_name: 'krishnaji' | 'preethaji' | 'combined'\n"
            "- interviewer_name: string (e.g. 'Marie Forleo' or 'Seeker')\n"
            "- seeker_question: string (question asked or dilemma expressed)\n"
            "- seeker_emotional_state: string (e.g. 'anxiety about wealth', 'fear of future', 'relationship strain')\n"
            "- guru_response: string (exact response text from Guru)\n"
            "- phrasing_dna: list of string phrases (e.g. ['beautiful state', 'from there nurture a life'])\n"
            "- teaching_concept: string (e.g. 'Beautiful State vs Suffering State')\n"
        )

        all_exemplars: list[PersonaToneExemplar] = []
        seen_prefixes: set[str] = set()

        for chunk_idx, chunk_text in enumerate(chunks):
            user_prompt = (
                f"Source ID: {source_id} (chunk {chunk_idx + 1}/{len(chunks)})\n\n"
                f"Transcript snippet:\n{chunk_text}\n\n"
                f"{extract_instruction}"
            )
            try:
                resp = await self.llm_service.generate(system_prompt, user_prompt, temperature=0.2)
                raw_json = resp.strip()
                start = raw_json.find("[")
                end = raw_json.rfind("]")
                if start == -1 or end == -1:
                    continue
                items = json.loads(raw_json[start: end + 1])
                for i, item in enumerate(items):
                    response_text = item.get("guru_response", "")
                    # Deduplicate by first 80 chars of response
                    prefix = response_text[:80].lower().strip()
                    if prefix in seen_prefixes or not response_text:
                        continue
                    seen_prefixes.add(prefix)
                    all_exemplars.append(
                        PersonaToneExemplar(
                            id=f"{source_id}_llm_c{chunk_idx}_{i}",
                            guru_name=item.get("guru_name", default_guru),
                            speaker_role=item.get("guru_name", default_guru),
                            interviewer_name=item.get("interviewer_name", "Interviewer/Seeker"),
                            seeker_question=item.get("seeker_question", ""),
                            seeker_emotional_state=item.get("seeker_emotional_state", "spiritual inquiry"),
                            guru_response=response_text,
                            phrasing_dna=item.get("phrasing_dna", []),
                            teaching_concept=item.get("teaching_concept", "Living in a Beautiful State"),
                            source_id=source_id,
                            raw_segment=response_text,
                        )
                    )
            except Exception as chunk_exc:
                logger.warning(
                    f"ToneExtractor: chunk {chunk_idx + 1}/{len(chunks)} extraction failed "
                    f"({chunk_exc}), skipping chunk."
                )
                continue

        if all_exemplars:
            logger.info(
                f"ToneExtractor: extracted {len(all_exemplars)} unique exemplars "
                f"from {len(chunks)} chunks of '{source_id}'."
            )
        return all_exemplars
