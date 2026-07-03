#!/usr/bin/env python3
"""Extract curated OKF entries from Qdrant, Neo4j, and LightRAG via LLM synthesis.

Andrej Karpathy LLM wiki pattern: LLM reads raw transcripts + entities →
synthesizes structured markdown entries → staging for admin review → compile.

Usage:
  python -m scripts.extract_okf_from_stores --all --limit 20
  python -m scripts.extract_okf_from_stores --topic "beautiful state" --limit 5
  python -m scripts.extract_okf_from_stores --video-id "TqxxCYnAxo8"
  python -m scripts.extract_okf_from_stores --all --auto-approve --limit 10
  python -m scripts.extract_okf_from_stores --all --dry-run

ponytail: CLI only — no Celery task until the extraction proves valuable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s"
)
logger = logging.getLogger(__name__)

_OKF_DIR = _BACKEND.parent / "memory" / "okf"
_STAGING_DIR = _OKF_DIR / "staging"
_VALID_TYPES = {"teaching", "practice", "glossary", "qa", "reflection"}

# ── doctrine tags (inlined to avoid ingest.pipeline import → ContainerBuilder OOM) ──

_DOCTRINE_SYNONYMS: dict[str, list[str]] = {
    # Core teachings
    "beautiful state": ["beautiful state", "blissful state", "state of bliss", "state of calm", "state of joy"],
    "suffering state": ["suffering state", "state of suffering", "painful state", "state of pain"],
    "surrender": ["surrender", "letting go", "giving up control", "relinquishing", "total surrender"],
    "oneness": ["oneness", "unity", "non-duality", "non-dual", "advaita", "non separation"],
    "consciousness": ["consciousness", "awareness", "higher consciousness", "divine consciousness", "universal consciousness"],
    "ekam": ["ekam", "ekam world", "world centre for enlightenment", "world center for enlightenment"],
    "deeksha": ["deeksha", "oneness blessing", "divine blessing", "energy transmission", "sacred transfer"],
    "soul sync": ["soul sync", "soul synchronization", "breath meditation", "breath awareness meditation"],
    "four sacred secrets": ["four sacred secrets", "4 sacred secrets", "sacred secrets", "the four secrets"],
    "sri preethaji": ["sri preethaji", "preethaji", "preetha ji", "sree preethaji"],
    "sri krishnaji": ["sri krishnaji", "krishnaji", "krishna ji", "sree krishnaji"],
    "meditation": ["meditation", "dhyana", "dhyan", "contemplation", "mindfulness practice"],
    "dharma": ["dharma", "righteousness", "righteous path", "duty", "cosmic order"],
    "karma": ["karma", "karmic", "action and consequence", "law of cause and effect"],
    "moksha": ["moksha", "liberation", "enlightenment", "spiritual freedom", "self-realization"],
    "atma": ["atma", "atman", "soul", "inner self", "higher self", "true self"],
    "brahman": ["brahman", "brahman", "universal self", "supreme reality", "absolute reality"],
    "samsara": ["samsara", "cycle of birth", "rebirth", "worldly cycle"],
    "guru": ["guru", "master", "spiritual teacher", "spiritual guide", "enlightened master"],
    "sadhna": ["sadhna", "sadhana", "spiritual practice", "spiritual discipline", "spiritual sadhana"],
    "sadhak": ["sadhak", "seeker", "spiritual seeker", "practitioner", "devotee"],
    "mahavakya": ["mahavakya", "great saying", "great pronouncement", "vedic statement"],
    "satsang": ["satsang", "spiritual gathering", "spiritual discourse", "divine gathering"],
    "sankalpa": ["sankalpa", "intention", "resolve", "sacred intention", "spiritual resolve"],
    "vairagya": ["vairagya", "dispassion", "detachment", "non-attachment", "renunciation"],
    "bhakti": ["bhakti", "devotion", "divine devotion", "loving devotion", "devotional practice"],
    "jnana": ["jnana", "knowledge", "spiritual knowledge", "divine wisdom", "higher knowledge"],
    "kriya": ["kriya", "action", "spiritual action", "sacred action", "purificatory practice"],
    "mantra": ["mantra", "sacred sound", "sacred syllable", "divine chant", "spiritual chant"],
    "mayic force": ["mayic force", "illusion force", "deluding force", "maya", "illusory power"],
    "dharma prabhu": ["dharma prabhu", "lord of dharma", "lord of righteousness", "divine lawkeeper"],
    "jeevan mukta": ["jeevan mukta", "jeevanmukta", "liberated while living", "living liberated one"],
    "paramatma": ["paramatma", "paramatman", "supreme soul", "universal soul", "supreme self"],
    "prarabdha": ["prarabdha", "prarabdha karma", "matured karma", "destined karma", "fruit of past actions"],
}


def _extract_doctrine_tags(text: str) -> list[str]:
    """Scan text for doctrinal synonyms, return matching canonical concepts.

    Inlined from ingest.pipeline to avoid importing the full ContainerBuilder
    (which loads bge-m3, LangGraph, LLM services — OOM in tight containers).
    """
    matched: set[str] = set()
    text_lower = text.lower()
    for canonical, alternates in _DOCTRINE_SYNONYMS.items():
        for alt in alternates:
            if re.search(r"\b" + re.escape(alt.lower()) + r"\b", text_lower):
                matched.add(canonical)
                break
    return list(matched)


# ── helpers ──────────────────────────────────────────────────────────────────


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return s or "entry"


def _write_okf_entry(
    title: str,
    type_: str,
    body: str,
    source: str | None = None,
    video_id: str | None = None,
    tags: list[str] | None = None,
    directory: Path | None = None,
) -> Path:
    """Write an OKF markdown entry to the given directory."""
    if type_ not in _VALID_TYPES:
        raise ValueError(f"invalid type {type_!r}; must be one of {_VALID_TYPES}")
    if not title.strip() or not body.strip():
        raise ValueError("title and body must be non-empty")

    target_dir = directory or _STAGING_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    fm = ["---", f"type: {type_}", f'title: "{title}"']
    if source:
        fm.append(f'source: "{source}"')
    if video_id:
        fm.append(f"video_id: {video_id}")
    if tags:
        fm.append(f"tags: [{', '.join(tags)}]")
    fm.append("---")
    content = "\n".join(fm) + "\n\n# " + title + "\n\n" + body.strip() + "\n"

    path = target_dir / f"{_slug(title)}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ── data gathering ───────────────────────────────────────────────────────────


async def _gather_qdrant_chunks(limit: int | None = None) -> list[dict]:
    """Fetch all text chunks from Qdrant, optionally capped."""
    import asyncio

    from services.qdrant_service import QdrantService

    svc = QdrantService()
    try:
        raw = await asyncio.to_thread(svc.get_all_texts)
    except Exception as exc:
        logger.error("Qdrant scan failed: %s", exc)
        return []

    if limit and len(raw) > limit:
        raw = raw[:limit]
    logger.info("Qdrant: %d chunks loaded", len(raw))
    return raw


async def _gather_neo4j_entities() -> list[dict[str, str]]:
    """Fetch all named entities from Neo4j."""
    from app.config import settings

    if not getattr(settings, "neo4j_uri", None):
        logger.warning("Neo4j not configured — skipping entity query")
        return []

    try:
        from neo4j import GraphDatabase

        def _fetch():
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            entities = []
            with driver.session() as session:
                result = session.run(
                    "MATCH (n) WHERE n.entity_id IS NOT NULL "
                    "RETURN n.entity_id AS name, n.description AS desc, "
                    "n.entity_type AS type LIMIT 200"
                )
                for r in result:
                    entities.append({
                        "name": r["name"] or "",
                        "desc": r["desc"] or "",
                        "type": r["type"] or "concept",
                    })
            return entities

        entities = await asyncio.to_thread(_fetch)
        logger.info("Neo4j: %d entities loaded", len(entities))
        return entities
    except Exception as exc:
        logger.warning("Neo4j entity fetch failed: %s", exc)
        return []


async def _gather_lightrag_relationships(
    queries: list[str],
) -> dict[str, str]:
    """Query LightRAG for entity-relationship context per topic."""
    results: dict[str, str] = {}
    if not queries:
        return results

    try:
        from services.lightrag_service import LightRAGService

        rag = LightRAGService()
        await rag.initialize()

        for q in queries:
            try:
                ctx = await rag.aquery(q, mode="hybrid", only_need_context=True)
                if ctx:
                    results[q] = ctx[:2000]  # ponytail: cap to avoid prompt bloat
            except Exception as exc:
                logger.debug("LightRAG query skipped for %r: %s", q, exc)
    except Exception as exc:
        logger.warning("LightRAG unavailable: %s", exc)

    logger.info("LightRAG: %d relationship sets gathered", len(results))
    return results


# ── topic clustering ─────────────────────────────────────────────────────────


def _cluster_chunks_by_topic(chunks: list[dict]) -> dict[str, list[dict]]:
    """Group Qdrant chunks by topic field (primary) or source_url (fallback)."""
    clustered: dict[str, list[dict]] = {}
    for c in chunks:
        key = c.get("topic", "") or c.get("source_url", "unknown")
        if key not in clustered:
            clustered[key] = []
        clustered[key].append(c)
    return clustered


async def _get_topic_clusters(
    chunks: list[dict],
    target_topic: str | None = None,
    target_video_id: str | None = None,
    limit: int = 20,
    *,
    skip_heavy: bool = False,
) -> list[dict[str, Any]]:
    """Build topic clusters with chunks, entities, and LightRAG context.

    When ``skip_heavy`` is True (dry-run), Neo4j & LightRAG are skipped —
    avoids OOM from loading bge-m3 + LangGraph in memory-constrained containers.
    """
    # Filter by video_id if specified
    if target_video_id:
        chunks = [c for c in chunks if target_video_id in c.get("source_url", "")]
        if not chunks:
            logger.warning("No chunks found for video_id=%s", target_video_id)
            return []

    # Group by topic
    by_topic = _cluster_chunks_by_topic(chunks)

    # If target_topic specified, filter topics containing it
    if target_topic:
        matched = {}
        for k, v in by_topic.items():
            if target_topic.lower() in k.lower():
                matched[k] = v
        if matched:
            by_topic = matched
        else:
            # ponytail: fuzzy match — try any chunk whose text contains the topic
            matched = {"custom": []}
            for c in chunks:
                if target_topic.lower() in c.get("text", "").lower():
                    matched["custom"].append(c)
            by_topic = matched

    # Sort by chunk count, take top N
    ranked = sorted(by_topic.items(), key=lambda kv: len(kv[1]), reverse=True)
    if limit:
        ranked = ranked[:limit]

    # Fetch Neo4j entities — skip in dry-run to avoid heavyweight service init
    entities: list[dict] = []
    if not skip_heavy:
        entities = await _gather_neo4j_entities()

    clusters = []
    for topic_key, topic_chunks in ranked:
        # Collect unique speakers, source URLs, and sample texts
        speakers = list({c.get("speaker", "Unknown") for c in topic_chunks})
        sources = list({c.get("source_url", "") for c in topic_chunks})
        titles = list({c.get("title", "") for c in topic_chunks if c.get("title")})

        # Truncate chunk texts to avoid prompt overload (3000 chars max)
        combined_text = "\n\n".join(
            c.get("text", "")[:500] for c in topic_chunks[:8]
        )[:3000]

        # Find relevant entities (inlined _extract_doctrine_tags — avoids OOM)
        topic_tags = _extract_doctrine_tags(
            topic_key + " " + " ".join(c.get("text", "")[:200] for c in topic_chunks[:5])
        )
        relevant_entities = [
            e for e in entities
            if any(t.lower() in (e.get("name", "") + " " + e.get("desc", "")).lower()
                   for t in topic_tags)
        ]
        if not relevant_entities:
            relevant_entities = entities[:10]  # ponytail: use top entities as context

        clusters.append({
            "topic_key": topic_key,
            "chunk_count": len(topic_chunks),
            "speakers": speakers,
            "sources": sources,
            "titles": titles,
            "combined_text": combined_text,
            "entities": relevant_entities,
            "tags": topic_tags,
        })

    # Gather LightRAG context for each cluster (parallel async) — skip in dry-run
    if not skip_heavy:
        lightrag_queries = [c["topic_key"] for c in clusters[:10]]
        lr_results = await _gather_lightrag_relationships(lightrag_queries)
        for c in clusters:
            c["lightrag_context"] = lr_results.get(c["topic_key"], "")
    else:
        for c in clusters:
            c["lightrag_context"] = ""

    logger.info(
        "Clusters: %d topics (limit=%s, topic=%s, video=%s, skip_heavy=%s)",
        len(clusters), limit, target_topic or "any", target_video_id or "any", skip_heavy,
    )
    return clusters


# ── LLM synthesis ────────────────────────────────────────────────────────────


def _build_okf_prompt(cluster: dict[str, Any]) -> tuple[str, str]:
    """Build system + user prompt for OKF entry generation. Zero-hallucination: only
    content from provided transcripts/entities may appear in the output."""
    system = (
        "You are a careful knowledge curator for Mukthi Guru, a spiritual guide "
        "grounded in the teachings of Sri Preethaji and Sri Krishnaji.\n\n"
        "CRITICAL RULES:\n"
        "1. ONLY use content from the provided transcripts and entities below.\n"
        "2. Do NOT invent teachings, quotes, concepts, or facts.\n"
        "3. Preserve the original speaker's voice.\n"
        "4. If you are unsure about something, omit it — do not fabricate.\n"
        "5. Always cite the source YouTube video in the source field.\n\n"
        "Output format — valid YAML frontmatter + markdown body:\n"
        "---\n"
        "type: teaching  # one of: teaching, practice, glossary, qa, reflection\n"
        'title: "Title Here"\n'
        'source: "YouTube https://www.youtube.com/watch?v=VIDEO_ID"\n'
        'tags: [tag1, tag2]\n'
        "---\n\n"
        "# Title\n\n"
        "## Summary\n"
        "A clear, concise summary grounded ONLY in the provided transcripts.\n\n"
        "## Key Teachings\n"
        "- Teaching point 1 (with speaker attribution: \"Sri Preethaji says...\")\n"
        "- Teaching point 2\n\n"
        "## Quotes\n"
        "> \"Exact quote from transcript\" — Sri Krishnaji\n\n"
        "## Related Concepts\n"
        "- concept name: brief description\n\n"
        "Do NOT include preamble like \"Here is the entry\" — output ONLY the "
        "YAML frontmatter and markdown body."
    )

    entity_lines = "\n".join(
        f"- {e['name']} ({e.get('type', 'concept')}): {e.get('desc', '')[:200]}"
        for e in cluster.get("entities", [])[:15]
    )
    lr_context = cluster.get("lightrag_context", "")

    user = (
        f"TOPIC: {cluster['topic_key']}\n"
        f"SPEAKERS: {', '.join(cluster.get('speakers', ['Unknown']))}\n"
        f"SOURCE VIDEOS: {', '.join(cluster.get('sources', []))}\n"
        f"VIDEO TITLES: {', '.join(cluster.get('titles', []))}\n"
        f"DOCTRINE TAGS: {', '.join(cluster.get('tags', []))}\n\n"
        f"─── SOURCE TRANSCRIPTS (from YouTube videos) ───\n\n"
        f"{cluster['combined_text']}\n\n"
        f"─── RELATED ENTITIES (from knowledge graph) ───\n\n"
        f"{entity_lines or '(none)'}\n\n"
        f"─── ENTITY RELATIONSHIPS (from LightRAG) ───\n\n"
        f"{lr_context or '(none)'}\n\n"
        f"Generate ONE OKF markdown entry for the topic \"{cluster['topic_key']}\" "
        f"using ONLY the content above. Choose the most appropriate type "
        f"(teaching/practice/glossary/qa/reflection).\n"
    )

    return system, user


async def _call_llm(system: str, user: str) -> str:
    """Generate OKF entry via the configured LLM provider with auto-failover."""
    from app.config import settings

    provider = getattr(settings, "llm_provider", "sarvam_cloud")

    # Try multi-provider LLM first
    try:
        from services.multi_provider_llm import MultiProviderLLMService

        llm = MultiProviderLLMService()
        result = await llm.generate(
            prompt=f"{system}\n\n{user}",
            max_tokens=2048,
            temperature=0.3,
        )
        text = result.get("text") or result.get("content") or result.get("response", "")
        if text:
            logger.info("LLM: generated %d chars via multi-provider", len(text))
            return text.strip()
    except Exception as exc:
        logger.warning("Multi-provider LLM failed: %s — trying OpenRouter", exc)

    # Fallback: OpenRouter direct
    try:
        from services.openrouter_service import OpenRouterService

        ors = OpenRouterService()
        text = await ors.generate(
            system_prompt=system,
            user_prompt=user,
            temperature=0.3,
            max_tokens=2048,
        )
        if text:
            logger.info("LLM: generated %d chars via OpenRouter", len(text))
            return text.strip()
    except Exception as exc:
        logger.warning("OpenRouter LLM failed: %s — trying Ollama", exc)

    # Final fallback: Ollama (local — always available if ollama serve is running)
    try:
        from services.ollama_service import OllamaService

        ollama = OllamaService()
        text = await ollama.generate(
            system_prompt=system,
            user_prompt=user,
            temperature=0.3,
            operation="okf_extraction",
        )
        if text:
            logger.info("LLM: generated %d chars via Ollama", len(text))
            return text.strip()
    except Exception as exc:
        logger.warning("Ollama LLM failed: %s", exc)

    raise RuntimeError("No LLM provider available — ensure llm_provider is configured")


def _parse_okf_response(raw: str) -> dict[str, Any] | None:
    """Parse LLM output into structured OKF fields — robust to messy output."""
    # Strip preamble like "Here is the entry" or code fences
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()

    # Extract frontmatter between first --- and second ---
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        logger.warning("No YAML frontmatter found in LLM output")
        return None

    fm_text = fm_match.group(1)
    body = text[fm_match.end():].strip()

    # Parse frontmatter manually (avoid YAML dependency)
    frontmatter: dict[str, Any] = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # Handle tags list: [a, b, c]
        if key == "tags" and val.startswith("[") and val.endswith("]"):
            val = [t.strip().strip('"').strip("'") for t in val[1:-1].split(",")]
        frontmatter[key] = val

    required = {"type", "title"}
    missing = required - set(frontmatter.keys())
    if missing:
        logger.warning("Missing frontmatter fields: %s", missing)
        return None

    if frontmatter.get("type") not in _VALID_TYPES:
        logger.warning(
            "Invalid type %r — defaulting to 'teaching'", frontmatter.get("type")
        )
        frontmatter["type"] = "teaching"

    return {
        "title": frontmatter["title"],
        "type": frontmatter["type"],
        "source": frontmatter.get("source", ""),
        "tags": frontmatter.get("tags", []),
        "body": body,
    }


# ── orchestration ────────────────────────────────────────────────────────────


async def extract_okf(
    *,
    target_topic: str | None = None,
    target_video_id: str | None = None,
    limit: int = 20,
    auto_approve: bool = False,
    dry_run: bool = False,
    chunk_limit: int | None = None,
) -> list[Path]:
    """Main extraction pipeline: scan stores → cluster → LLM synthesize → write."""
    logger.info(
        "OKF extraction start: topic=%s, video=%s, limit=%d, auto=%s, dry=%s",
        target_topic or "any", target_video_id or "any",
        limit, auto_approve, dry_run,
    )

    # 1. Gather data from all stores
    chunks = await _gather_qdrant_chunks(limit=chunk_limit)
    if not chunks:
        logger.warning("No Qdrant chunks available — cannot extract OKF entries")
        return []

    # 2. Cluster by topic (skip Neo4j/LightRAG in dry-run — avoid OOM)
    clusters = await _get_topic_clusters(
        chunks,
        target_topic=target_topic,
        target_video_id=target_video_id,
        limit=limit,
        skip_heavy=dry_run,
    )
    if not clusters:
        logger.warning("No topic clusters found")
        return []

    # 3. LLM synthesis for each cluster
    written: list[Path] = []
    target_dir = _OKF_DIR if auto_approve else _STAGING_DIR

    for i, cluster in enumerate(clusters):
        logger.info(
            "[%d/%d] Generating OKF entry for: %s (%d chunks)",
            i + 1, len(clusters), cluster["topic_key"], cluster["chunk_count"],
        )

        system, user = _build_okf_prompt(cluster)

        if dry_run:
            logger.info("DRY-RUN prompt (system=%d chars, user=%d chars)",
                        len(system), len(user))
            logger.info("Would write to: %s/%s.md",
                        target_dir, _slug(cluster["topic_key"]))
            continue

        try:
            raw = await _call_llm(system, user)
            parsed = _parse_okf_response(raw)
            if not parsed:
                logger.warning("Failed to parse LLM output for %s — skipping",
                               cluster["topic_key"])
                continue

            source_url = cluster.get("sources", [""])[0] if cluster.get("sources") else None
            video_id = None
            if source_url and "watch?v=" in source_url:
                video_id = source_url.split("watch?v=")[-1].split("&")[0]

            path = _write_okf_entry(
                title=parsed["title"],
                type_=parsed["type"],
                body=parsed["body"],
                source=parsed.get("source") or source_url,
                video_id=video_id,
                tags=parsed.get("tags", cluster.get("tags", [])),
                directory=target_dir,
            )
            written.append(path)
            logger.info("  → %s", path)
        except Exception as exc:
            logger.error("Entry generation failed for %s: %s",
                         cluster["topic_key"], exc)

    # 4. Compile if auto-approved
    if auto_approve and written:
        logger.info("Auto-approve: compiling OKF index")
        try:
            from services.memory.compiler import compile_okf

            compile_okf()
            logger.info("OKF compiled.json updated with %d entries", len(written))
        except Exception as exc:
            logger.error("Compile failed: %s", exc)

    logger.info(
        "OKF extraction done: %d entries written to %s (staged=%s)",
        len(written), target_dir, not auto_approve,
    )
    return written


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(
        description="LLM-powered OKF extraction from Qdrant, Neo4j, and LightRAG",
    )
    p.add_argument("--all", action="store_true",
                   help="Extract from all available sources")
    p.add_argument("--topic", default=None,
                   help="Extract specific topic (e.g. 'beautiful state')")
    p.add_argument("--video-id", default=None,
                   help="Extract from a specific YouTube video ID")
    p.add_argument("--limit", type=int, default=20,
                   help="Max topic clusters to process (default: 20)")
    p.add_argument("--auto-approve", action="store_true",
                   help="Write directly to memory/okf/ and trigger compile")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be generated without writing files")
    p.add_argument("--chunk-limit", type=int, default=None,
                   help="Max Qdrant chunks to scan (default: unlimited)")
    args = p.parse_args()

    if not args.all and not args.topic and not args.video_id:
        p.error("Specify --all, --topic, or --video-id")

    written = asyncio.run(
        extract_okf(
            target_topic=args.topic,
            target_video_id=args.video_id,
            limit=args.limit,
            auto_approve=args.auto_approve,
            dry_run=args.dry_run,
            chunk_limit=args.chunk_limit,
        )
    )

    if args.dry_run:
        print("Dry run complete — no files written.")
    else:
        print(f"OKF extraction complete: {len(written)} entries written.")
        for p in written:
            print(f"  {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())