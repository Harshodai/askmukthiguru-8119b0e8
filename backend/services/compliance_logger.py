"""
Unit 24 — Compliance & Audit Logging

Provides GDPR-safe audit logging for all LLM interactions.

Design decisions:
  - Prompts are SHA-256 hashed — plaintext is NEVER stored.
  - Responses are truncated to 500 chars for audit trail (not full storage).
  - Tenant ID and user ID are stored for data deletion requests (GDPR Art. 17).
  - Log format: newline-delimited JSON (NDJSON) for easy streaming / ingestion.
  - Storage: local JSONL file (compliance_audit.jsonl in the backend directory).
    Rotate daily using a timestamp suffix.

Log record schema:
  {
    "ts": "ISO-8601",            # UTC timestamp
    "tenant_id": "...",          # From TenantContext
    "user_id": "...",            # From auth JWT (sub claim)
    "session_id": "...",         # Request-level UUID
    "action": "generate|stream|classify",
    "model": "gemma3:12b|...",
    "prompt_hash": "sha256:...", # Hash of system+user prompts
    "response_preview": "...",   # First 500 chars of response
    "tokens_in": 123,            # Estimated input tokens
    "tokens_out": 456,           # Estimated output tokens
    "latency_ms": 789,           # Wall-clock ms
    "status": "ok|error",        # Outcome
    "error": "..."               # Only on status=error
  }
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------
_DEFAULT_AUDIT_DIR = Path(os.environ.get("COMPLIANCE_AUDIT_DIR", "/var/log/mukthi-guru"))
_AUDIT_FILE_PREFIX = "compliance_audit"
_MAX_RESPONSE_PREVIEW = 500


def _get_audit_path(base_dir: Path = _DEFAULT_AUDIT_DIR) -> Path:
    """Return today's NDJSON audit log file path."""
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return base_dir / f"{_AUDIT_FILE_PREFIX}_{today}.jsonl"


def _hash_prompt(text: str) -> str:
    """SHA-256 hash of the prompt text — GDPR-safe, no plaintext stored."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------
# ComplianceLogger
# -----------------------------------------------------------------------

class ComplianceLogger:
    """GDPR-compliant audit logger for all LLM interactions.

    Thread-safe: each write is a single ``f.write()`` call which is atomic on
    POSIX-compliant filesystems for writes < PIPE_BUF (~4 KB).

    Usage::

        logger = ComplianceLogger()
        session_id = logger.start_session(tenant_id, user_id)

        with logger.record(session_id, action="generate", model="gemma3:12b") as ctx:
            ctx.log_prompt(system_prompt, user_prompt)
            result = await ollama.generate(...)
            ctx.log_response(result, tokens_in=100, tokens_out=50)
    """

    def __init__(self, audit_dir: Optional[Path] = None) -> None:
        self._audit_dir = audit_dir or _DEFAULT_AUDIT_DIR
        try:
            self._audit_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # In sandboxed / read-only environments, fall back to local dir
            logger.warning(
                f"ComplianceLogger: cannot create {self._audit_dir}: {exc}. "
                f"Falling back to ./logs/"
            )
            self._audit_dir = Path("logs")
            self._audit_dir.mkdir(parents=True, exist_ok=True)

    # ---- Session API ----

    def start_session(self, tenant_id: str = "default", user_id: str = "") -> str:
        """Generate a new session ID for a single request lifecycle."""
        return str(uuid.uuid4())

    # ---- Low-level record writing ----

    def write_record(self, record: dict) -> None:
        """Append a single audit record to today's JSONL file."""
        path = _get_audit_path(self._audit_dir)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error(f"ComplianceLogger: failed to write audit record: {exc}")

    # ---- High-level convenience API ----

    def log_interaction(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        action: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> None:
        """Log a single completed LLM interaction."""
        combined_prompt = system_prompt + "\n" + user_prompt
        record = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "action": action,
            "model": model,
            "prompt_hash": _hash_prompt(combined_prompt),
            "response_preview": response[:_MAX_RESPONSE_PREVIEW],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 2),
            "status": status,
        }
        if error:
            record["error"] = error[:500]
        self.write_record(record)

    def log_error(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        action: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        error: str,
        latency_ms: float = 0.0,
    ) -> None:
        """Log a failed interaction with error details."""
        self.log_interaction(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            action=action,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response="",
            latency_ms=latency_ms,
            status="error",
            error=error,
        )

    # ---- GDPR data deletion support ----

    def list_sessions_for_user(self, user_id: str, days: int = 30) -> list[dict]:
        """Return all audit records for a specific user ID (for GDPR Art. 17 requests).

        Reads up to ``days`` of log files. Does NOT return prompt content (hashed only).
        """
        records = []
        for path in sorted(self._audit_dir.glob(f"{_AUDIT_FILE_PREFIX}_*.jsonl"))[-days:]:
            try:
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                            if rec.get("user_id") == user_id:
                                records.append(rec)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue
        return records


# -----------------------------------------------------------------------
# Singleton
# -----------------------------------------------------------------------
_compliance_logger: Optional[ComplianceLogger] = None


def get_compliance_logger() -> ComplianceLogger:
    """Return the singleton ComplianceLogger instance."""
    global _compliance_logger
    if _compliance_logger is None:
        _compliance_logger = ComplianceLogger()
    return _compliance_logger
