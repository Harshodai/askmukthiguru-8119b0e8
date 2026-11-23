"""Data models for Keyword Research product workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SearchIntent(str, Enum):
    INFORMATIONAL = "Informational"
    NAVIGATIONAL = "Navigational"
    COMMERCIAL = "Commercial"
    TRANSACTIONAL = "Transactional"


class KDLevel(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class KeywordItem:
    keyword: str
    topic_cluster: str
    search_intent: SearchIntent
    monthly_volume: int
    global_volume: int
    kd: int
    kd_level: KDLevel
    cpc: float
    parent_topic: str
    content_type: str
    priority: Priority


@dataclass
class CompetitorItem:
    domain: str
    traffic_share_pct: float
    traffic_value: float
    domain_rating: int
    observations: str


@dataclass
class KeywordGapItem:
    competitor_keyword: str
    top_competitor: str
    volume: int
    kd: int
    recommended_action: str


@dataclass
class KeywordResearchPayload:
    seed_keyword: str
    target_country: str
    data_source: str
    volume_scope_label: str
    keywords: list[KeywordItem] = field(default_factory=list)
    competitors: list[CompetitorItem] = field(default_factory=list)
    gaps: list[KeywordGapItem] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    provenance: Optional[Mapping[str, Any]] = None
    production_certified: bool = False
    is_simulated: bool = False
