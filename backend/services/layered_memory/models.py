from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

MemoryType = Literal["persona", "episodic", "instruction"]


@dataclass
class MemoryAtom:
    content: str
    type: MemoryType
    priority: int
    source_message_ids: list[str]
    scene_name: str
    metadata: dict[str, Any]
    id: Optional[str] = None
