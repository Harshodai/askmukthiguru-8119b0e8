"""Doctrine Service — Load and inject synonyms per guru/assistant."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class DoctrineService:
    """Load and cache doctrines per guru/assistant."""

    def __init__(self, supabase_client: Any = None) -> None:
        self._supabase = supabase_client
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_fetch: dict[str, float] = {}

    def _get_client(self) -> Any:
        if self._supabase:
            return self._supabase
        if settings.supabase_url and settings.supabase_key:
            from supabase import create_client

            try:
                self._supabase = create_client(settings.supabase_url, settings.supabase_key)
                return self._supabase
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase in DoctrineService: {e}")
        return None

    async def get_doctrine(self, assistant_slug: str) -> dict[str, Any]:
        """Fetch and cache doctrine metadata for an assistant."""
        import asyncio
        now = time.time()

        # Check cache
        if assistant_slug in self._cache:
            if now - self._last_fetch.get(assistant_slug, 0) < self._cache_ttl:
                return self._cache[assistant_slug]

        client = self._get_client()
        if client:
            try:
                def _fetch():
                    return (
                        client.table("assistant_doctrines")
                        .select("*")
                        .eq("assistant_slug", assistant_slug)
                        .execute()
                    )

                res = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=1.5)
                if res and getattr(res, "data", None):
                    doc = res.data[0]
                    self._cache[assistant_slug] = doc
                    self._last_fetch[assistant_slug] = now
                    return doc
            except Exception as e:
                logger.debug(f"Failed to fetch doctrine from DB for {assistant_slug} (non-fatal): {e}")

        # Return cached fallback and cache negative hit for TTL to prevent blocking next turns
        fallback = {"synonyms_json": {}, "canonical_terms": []}
        self._cache[assistant_slug] = fallback
        self._last_fetch[assistant_slug] = now
        return fallback

    async def inject_doctrine_keywords(self, query: str, assistant_slug: str) -> str:
        """Enhance query with canonical terms if variants are found in the query."""
        doc = await self.get_doctrine(assistant_slug)
        synonyms = doc.get("synonyms_json") or {}

        enhanced = query
        query_lower = query.lower()

        for canonical, variants in synonyms.items():
            canonical_lower = canonical.lower()
            # If variant is found but canonical term itself is not mentioned, append it
            for variant in variants:
                variant_lower = variant.lower()
                if variant_lower in query_lower and canonical_lower not in query_lower:
                    enhanced += f" {canonical}"
                    break  # Only append canonical once

        return enhanced
