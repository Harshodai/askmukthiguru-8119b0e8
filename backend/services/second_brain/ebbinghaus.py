"""
Ebbinghaus forgetting curve and cognitive memory retention scoring
for the per-user Second Brain (Mukthi Vault).

Based on Hermann Ebbinghaus's spacing effect and cognitive agent memory architectures:
R(delta_days, access_count) = exp(-delta_days / (stability_days * (1 + beta * (access_count ** gamma))))
"""

from __future__ import annotations

import math
import time
from typing import Optional


def ebbinghaus_retention(
    delta_days: float,
    access_count: int = 0,
    stability_days: float = 30.0,
    beta: float = 0.45,
    gamma: float = 0.8,
) -> float:
    """Calculate the Ebbinghaus memory retention probability [0.0, 1.0].

    Args:
        delta_days: Elapsed days since creation or last recall.
        access_count: Number of times this memory was retrieved/reinforced.
        stability_days: Baseline half-life/stability of memory in days (default 30.0).
        beta: Spaced repetition reinforcement coefficient (default 0.45).
        gamma: Sub-linear scaling factor for access count (default 0.8).

    Returns:
        Retention factor between 0.0 and 1.0.
    """
    if delta_days <= 0.0:
        return 1.0

    access_count = max(0, int(access_count))
    effective_stability = stability_days * (1.0 + beta * (access_count**gamma))
    if effective_stability <= 0.0:
        return 0.0

    return float(math.exp(-delta_days / effective_stability))


def score_memory_candidate(
    similarity: float,
    created_at_epoch: float,
    access_count: int = 0,
    is_superseded: bool = False,
    decay_factor: float = 0.05,
    current_epoch: Optional[float] = None,
    stability_days: float = 30.0,
) -> float:
    """Combine vector similarity, Ebbinghaus decay, and superseded penalty.

    Args:
        similarity: Cosine similarity or reciprocal rank score [0.0, 1.0].
        created_at_epoch: Creation or last-touched timestamp in epoch seconds.
        access_count: Number of times the item has been accessed.
        is_superseded: True if newer information superseded this memory.
        decay_factor: Heavy penalty factor for superseded memories (default 0.05).
        current_epoch: Optional current timestamp (defaults to time.time()).
        stability_days: Baseline stability in days (default 30.0).

    Returns:
        Final composite memory score.
    """
    now = time.time() if current_epoch is None else float(current_epoch)
    delta_seconds = max(0.0, now - float(created_at_epoch))
    delta_days = delta_seconds / 86400.0

    retention = ebbinghaus_retention(
        delta_days=delta_days,
        access_count=access_count,
        stability_days=stability_days,
    )
    superseded_penalty = float(decay_factor) if is_superseded else 1.0

    return float(similarity * retention * superseded_penalty)
