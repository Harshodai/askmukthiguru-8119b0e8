"""Reusable Qdrant metadata filter builders."""

from __future__ import annotations

from typing import Optional

from qdrant_client.http.models import FieldCondition, Filter, MatchAny, MatchValue


class QdrantFilterBuilder:
    """Composable Qdrant payload filters for retrieval scoping."""

    @staticmethod
    def build_source_url_filter(source_url: str) -> Filter:
        """Return a Qdrant filter matching a specific source URL."""
        return Filter(
            must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
        )

    @staticmethod
    def build_source_type_filter(source_type: str) -> Filter:
        """Return a Qdrant filter matching a source_type (youtube/image/text/video/etc.)."""
        return Filter(
            must=[FieldCondition(key="source_type", match=MatchValue(value=source_type))]
        )

    @staticmethod
    def build_language_filter(language: str) -> Filter:
        """Return a Qdrant filter matching a detected language code."""
        return Filter(
            must=[FieldCondition(key="language", match=MatchValue(value=language))]
        )

    @staticmethod
    def build_tags_filter(tags: list[str] | str) -> Filter:
        """Return a Qdrant filter matching one or more tags."""
        tag_values = tags if isinstance(tags, list) else [tags]
        if len(tag_values) == 1:
            return Filter(
                must=[FieldCondition(key="tags", match=MatchValue(value=tag_values[0]))]
            )
        return Filter(
            must=[FieldCondition(key="tags", match=MatchAny(any=tag_values))]
        )

    @staticmethod
    def build_title_filter(title: str) -> Filter:
        """Return a Qdrant filter matching an exact title (useful for scoped retrieval)."""
        return Filter(
            must=[FieldCondition(key="title", match=MatchValue(value=title))]
        )

    @classmethod
    def build_metadata_filter(
        cls,
        source_url: Optional[str] = None,
        source_type: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[list[str] | str] = None,
        title: Optional[str] = None,
        content_type: Optional[str] = None,
        raptor_level: Optional[int] = None,
    ) -> Filter:
        """
        Compose a Qdrant filter from available metadata fields.

        All provided conditions are combined with AND semantics.
        """
        conditions: list[FieldCondition] = []
        if source_url:
            conditions.append(FieldCondition(key="source_url", match=MatchValue(value=source_url)))
        if source_type:
            conditions.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))
        if language:
            conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
        if tags:
            tag_values = tags if isinstance(tags, list) else [tags]
            if len(tag_values) == 1:
                conditions.append(FieldCondition(key="tags", match=MatchValue(value=tag_values[0])))
            else:
                conditions.append(FieldCondition(key="tags", match=MatchAny(any=tag_values)))
        if title:
            conditions.append(FieldCondition(key="title", match=MatchValue(value=title)))
        if content_type:
            conditions.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
        if raptor_level is not None:
            conditions.append(FieldCondition(key="raptor_level", match=MatchValue(value=raptor_level)))

        return Filter(must=conditions)
