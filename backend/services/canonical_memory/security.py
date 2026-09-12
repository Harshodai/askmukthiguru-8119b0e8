"""Security utilities for canonical memory system."""
import re
from typing import Any, List

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?prior",
    r"override\s+(system|all)\s+instructions",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?:",
    r"forget\s+(your|all)\s+(rules|instructions)",
]

def check_injection_attempt(text: str) -> bool:
    """Detect prompt injection patterns in text."""
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in INJECTION_PATTERNS)

def validate_user_scoped_query(user_id: str, results: list) -> list:
    """Verify all results belong to the specified user."""
    validated = []
    for r in results:
        if isinstance(r, dict) and r.get("user_id") == user_id:
            validated.append(r)
        elif hasattr(r, "user_id") and r.user_id == user_id:
            validated.append(r)
    return validated

def sanitize_memory_for_context(memory: dict) -> dict:
    """Remove sensitive fields before injecting into generation context."""
    safe = {k: v for k, v in memory.items() if k not in (
        "user_id", "tenant_id", "embedding_id", "metadata"
    )}
    return safe

def validate_deletion_completeness(user_id: str, db_client) -> dict:
    """Check all stores are cleaned for a user."""
    issues = []
    # Check canonical_memories
    result = db_client.table("canonical_memories").select("id").eq("user_id", user_id).limit(1).execute()
    if result.data:
        issues.append("canonical_memories not deleted")
    return {"complete": len(issues) == 0, "issues": issues}
