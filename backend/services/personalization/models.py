"""
Unified Personalization Models for AskMukthiGuru.

Unifies ALL user-based personalizations into a single coherent model:
1. Seeker Profile (spiritual readiness, tradition, language, tone, preferred guru, distress level)
2. Personal Knowledge Graph / Second Brain (canonical memories, cognitive memory entities, observations)
3. Sadhana Streaks & Daily Practices (streaks, daily practices, minutes meditated, consistency score)
4. Pre-Practice Logs & Intentions (mental clarity, emotional tone, pre-session state)
5. Study Notebooks & Saved Teachings (bookmarked clips, reflections, study tags)
6. Mood Trajectory & Spiritual Journal (mood history, growth reflections, journal entries)
7. WhatsApp Reflections & Voice Note Insights (messaging reflections, voice note insights)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from services.personalization.crypto import EncryptedFacet


class SeekerProfileContext(BaseModel):
    """Seeker spiritual profile and pedagogical guidance preferences."""

    spiritual_readiness: str = "seeker"  # beginner | explorer | practitioner | seeker | stabilized
    tradition: str = "universal"  # advaita | integral | yoga | general_vedanta | universal
    tone: str = "compassionate"  # compassionate | reverent | philosophical | direct
    preferred_guru: str = "any"  # Sri Amma Bhagavan | Sri Preethaji | Sri Krishnaji | any
    language: str = "en"
    distress_level: int = 0  # 0=NONE, 1=MILD, 2=MODERATE, 3=SEVERE, 4=CRISIS
    custom_attributes: dict[str, Any] = Field(default_factory=dict)
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class SecondBrainItem(BaseModel):
    """Individual item in the Second Brain knowledge graph."""

    id: str
    kind: str = "reflection"  # reflection | entity | preference | relationship | journal
    text: str
    confidence: float = 0.8
    created_at: float = 0.0
    access_count: int = 0
    properties: dict[str, Any] = Field(default_factory=dict)


class SecondBrainContext(BaseModel):
    """Personal Knowledge Graph & Second Brain memories."""

    canonical_memories: list[dict[str, Any]] = Field(default_factory=list)
    memory_entities: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    items: list[SecondBrainItem] = Field(default_factory=list)
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class SadhanaPracticeContext(BaseModel):
    """Sadhana practice history, streaks, and discipline consistency."""

    streak_count: int = 0
    longest_streak: int = 0
    daily_practices: list[str] = Field(default_factory=list)
    minutes_meditated: int = 0
    consistency_score: float = 1.0  # 0.0 to 1.0
    last_practice_date: Optional[str] = None
    freezes_available: int = 2
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class PrePracticeLogContext(BaseModel):
    """Pre-session inner climate, intentions, and mental clarity."""

    pre_session_state: str = "calm"  # calm | agitated | seeking clarity | restless
    intentions: list[str] = Field(default_factory=list)
    mental_clarity: int = 7  # 1 to 10 scale
    emotional_tone: str = "neutral"
    recent_logs: list[dict[str, Any]] = Field(default_factory=list)
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class StudyNotebookContext(BaseModel):
    """Study notebooks, saved teachings, bookmarked clips, and study tags."""

    notebooks: list[dict[str, Any]] = Field(default_factory=list)
    saved_teachings: list[dict[str, Any]] = Field(default_factory=list)
    study_tags: list[str] = Field(default_factory=list)
    active_reflections: list[str] = Field(default_factory=list)
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class MoodSpiritualJournalContext(BaseModel):
    """Mood trajectory, spiritual growth reflections, and deep journaling."""

    mood_trajectory: list[dict[str, Any]] = Field(default_factory=list)
    spiritual_growth_reflections: list[str] = Field(default_factory=list)
    journal_entries: list[dict[str, Any]] = Field(default_factory=list)
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class WhatsAppReflectionContext(BaseModel):
    """Integrated sadhana reflections from messaging and voice note insights."""

    reflections: list[dict[str, Any]] = Field(default_factory=list)
    voice_note_insights: list[str] = Field(default_factory=list)
    integration_status: str = "unlinked"  # active | unlinked | pending
    is_encrypted: bool = False
    encrypted_blob: Optional[EncryptedFacet] = None


class UnifiedSeekerContext(BaseModel):
    """
    Unified Seeker Context representing all personal dimensions of a spiritual seeker.
    Integrates 7 core personalization facets with Mode-B zero-knowledge protection.
    """

    user_id: str
    is_authenticated: bool = True
    tenant_id: str = "default"
    consent_flags: dict[str, bool] = Field(
        default_factory=lambda: {"personalization": False, "analytics": False, "storage": False}
    )
    hydration_latency_ms: float = 0.0
    seeker_profile: SeekerProfileContext = Field(default_factory=SeekerProfileContext)
    second_brain: SecondBrainContext = Field(default_factory=SecondBrainContext)
    sadhana: SadhanaPracticeContext = Field(default_factory=SadhanaPracticeContext)
    pre_practice: PrePracticeLogContext = Field(default_factory=PrePracticeLogContext)
    study_notebooks: StudyNotebookContext = Field(default_factory=StudyNotebookContext)
    mood_journal: MoodSpiritualJournalContext = Field(default_factory=MoodSpiritualJournalContext)
    whatsapp_reflections: WhatsAppReflectionContext = Field(
        default_factory=WhatsAppReflectionContext
    )
    mode_b_enabled: bool = False
    has_unlocked_vault: bool = False
    has_state_memory: bool = False
    hydrated_at: float = Field(default_factory=time.time)

    @model_validator(mode="before")
    @classmethod
    def _remap_legacy_field_names(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "sadhana_practice" in data and "sadhana" not in data:
                data["sadhana"] = data["sadhana_practice"]
            if "pre_practice_log" in data and "pre_practice" not in data:
                data["pre_practice"] = data["pre_practice_log"]
            if "study_notebook" in data and "study_notebooks" not in data:
                data["study_notebooks"] = data["study_notebook"]
            if "mood_spiritual_journal" in data and "mood_journal" not in data:
                data["mood_journal"] = data["mood_spiritual_journal"]
            if "whatsapp_reflection" in data and "whatsapp_reflections" not in data:
                data["whatsapp_reflections"] = data["whatsapp_reflection"]
        return data

    @property
    def sadhana_practice(self) -> SadhanaPracticeContext:
        return self.sadhana

    @property
    def pre_practice_log(self) -> PrePracticeLogContext:
        return self.pre_practice

    @property
    def study_notebook(self) -> StudyNotebookContext:
        return self.study_notebooks

    @property
    def mood_spiritual_journal(self) -> MoodSpiritualJournalContext:
        return self.mood_journal

    @property
    def whatsapp_reflection(self) -> WhatsAppReflectionContext:
        return self.whatsapp_reflections

    def format_prompt_guidance(self) -> str:
        """
        Formats all hydrated facets into high-density, structured prompt guidance
        for personalize_stage and GraphStage generation.
        Omits ciphertext when facets are Mode-B locked.
        """
        sections: list[str] = []

        # 1. Seeker Profile Guidance
        sp = self.seeker_profile
        sections.append("### Seeker Personalization & Spiritual Readiness")
        if sp.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted Profile: Client sealed]")
        else:
            sections.append(
                f"- **Readiness Level**: {sp.spiritual_readiness.title()} | "
                f"**Tradition**: {sp.tradition.title()} | "
                f"**Tone**: {sp.tone} | "
                f"**Preferred Guru**: {sp.preferred_guru}"
            )
            sections.append(
                f"- **Language**: {sp.language} | "
                f"**Distress Level**: {sp.distress_level} (0=None, 4=Crisis)"
            )
            topics = sp.custom_attributes.get("topics_of_interest")
            if topics:
                topics_str = ", ".join(topics) if isinstance(topics, list) else str(topics)
                sections.append(f"- **Focus Areas**: {topics_str}")

        # 2. Sadhana & Practices Journey
        sad = self.sadhana
        sections.append("\n### Sadhana & Practice Journey")
        if sad.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted Sadhana: Client sealed]")
        else:
            practices_str = (
                ", ".join(sad.daily_practices) if sad.daily_practices else "None recorded"
            )
            sections.append(
                f"- **Current Streak**: {sad.streak_count} days (Longest: {sad.longest_streak} days) | "
                f"**Consistency**: {int(sad.consistency_score * 100)}%"
            )
            sections.append(
                f"- **Total Meditated**: {sad.minutes_meditated} minutes | **Daily Practices**: {practices_str}"
            )

        # 3. Pre-Practice State & Intentions
        pp = self.pre_practice
        sections.append("\n### Pre-Practice State & Current Intentions")
        if pp.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted Pre-Practice: Client sealed]")
        else:
            intentions_str = "; ".join(pp.intentions) if pp.intentions else "General contemplation"
            sections.append(
                f"- **Mental Clarity**: {pp.mental_clarity}/10 | "
                f"**Inner State**: {pp.pre_session_state} | "
                f"**Emotional Tone**: {pp.emotional_tone}"
            )
            sections.append(f"- **Intentions**: {intentions_str}")

        # 4. Second Brain & Personal Knowledge Graph
        sb = self.second_brain
        sections.append("\n### Second Brain & Core Realizations")
        if sb.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted Second Brain: Client sealed]")
        else:
            if sb.canonical_memories:
                mems = [
                    m.get("statement", "") for m in sb.canonical_memories[:5] if m.get("statement")
                ]
                sections.append(f"- **Canonical Realizations**: {'; '.join(mems)}")
            if sb.observations:
                sections.append(f"- **Key Observations**: {'; '.join(sb.observations[:3])}")

        # 5. Study Notebooks & Saved Teachings
        sn = self.study_notebooks
        sections.append("\n### Study Notebooks & Saved Teachings")
        if sn.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted Notebooks: Client sealed]")
        else:
            if sn.saved_teachings:
                teachings = [t.get("title", "Teaching") for t in sn.saved_teachings[:3]]
                sections.append(f"- **Saved Teachings**: {', '.join(teachings)}")
            if sn.study_tags:
                sections.append(f"- **Study Focus Tags**: {', '.join(sn.study_tags[:5])}")

        # 6. Mood Trajectory & Spiritual Journal
        mj = self.mood_journal
        sections.append("\n### Mood Trajectory & Reflections")
        if mj.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted Mood & Journal: Client sealed]")
        else:
            if mj.spiritual_growth_reflections:
                sections.append(
                    f"- **Recent Reflections**: {'; '.join(mj.spiritual_growth_reflections[:2])}"
                )
            if mj.mood_trajectory:
                latest_mood = mj.mood_trajectory[-1].get("dominant_emotion", "balanced")
                sections.append(f"- **Dominant Emotional State**: {latest_mood}")

        # 7. WhatsApp Reflections & Voice Note Insights
        wa = self.whatsapp_reflections
        sections.append("\n### WhatsApp Sadhana Insights")
        if wa.is_encrypted and not self.has_unlocked_vault:
            sections.append("- [Mode-B Encrypted WhatsApp Insights: Client sealed]")
        else:
            if wa.voice_note_insights:
                sections.append(
                    f"- **Voice Note Insights**: {'; '.join(wa.voice_note_insights[:2])}"
                )
            elif wa.reflections:
                snippets = [
                    r.get("sadhana_reflection", "")
                    for r in wa.reflections[:2]
                    if r.get("sadhana_reflection")
                ]
                sections.append(f"- **Reflections**: {'; '.join(snippets)}")

        if self.mode_b_enabled and not self.has_unlocked_vault:
            sections.append(
                "\n*(Note: Client has enabled Mode-B Zero-Knowledge Vault. "
                "Private encrypted facets remain sealed on the server).* "
            )

        return "\n".join(sections)

    def to_safe_dict(self) -> dict[str, Any]:
        """
        Returns a clean dictionary representation.
        If a facet is Mode-B encrypted and locked, returns its encrypted envelope.
        """
        return self.model_dump()

    def export_all_user_data(self) -> dict[str, Any]:
        """
        Exports all 7 facets for GDPR Art 15 (Right of access) and DPDP Act 2023.
        """
        return {
            "user_id": self.user_id,
            "export_timestamp": time.time(),
            "mode_b_enabled": self.mode_b_enabled,
            "has_unlocked_vault": self.has_unlocked_vault,
            "facets": {
                "seeker_profile": self.seeker_profile.model_dump(),
                "second_brain": self.second_brain.model_dump(),
                "sadhana": self.sadhana.model_dump(),
                "pre_practice": self.pre_practice.model_dump(),
                "study_notebooks": self.study_notebooks.model_dump(),
                "mood_journal": self.mood_journal.model_dump(),
                "whatsapp_reflections": self.whatsapp_reflections.model_dump(),
            },
        }
