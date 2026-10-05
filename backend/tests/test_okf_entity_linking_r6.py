"""R6 entity-linking pre-pass (docs/OKF_WIRING_RESEARCH_2026-10-04.md).

Covers: linking precision on fixture queries (doctrine positives +
negatives), the OFF-by-default integration contract (inputs pass through
unchanged; trace-only), the enabled additive-only semantics, the
lexicon/synonym audit trail, and a retrieval-level no-op proof.
"""

from __future__ import annotations

import pytest

from rag.nodes.entity_linking import (
    _R6_EXTRA_ALIASES,
    link_entities,
    resolve_entity_links,
)

# (query, expected teachers, expected terms) — exact expectations, verified
# against the linker. Order of terms = first mention in the query.
POSITIVE_FIXTURES: list[tuple[str, list[str], list[str]]] = [
    ("How do I practice Soul Sync breath meditation?", [], ["Soul Sync", "Meditation"]),
    ("What is deeksha?", [], ["Deeksha"]),
    ("What did Preethaji say about the Beautiful State?", ["sri-preethaji"], ["Beautiful State"]),
    ("Tell me about diksha", [], ["Deeksha"]),
    ("Serene Mind practice steps", [], ["Serene Mind"]),
    ("What are the four sacred secrets?", [], ["Four Sacred Secrets"]),
    ("What does Sri Krishnaji teach about suffering?", ["sri-krishnaji"], []),
    ("Shri Preethaji on awakening", ["sri-preethaji"], ["Awakening"]),
    ("soul-sync technique", [], ["Soul Sync"]),
    ("Explain karma and moksha", [], ["Karma", "Moksha"]),
    ("What is the Ojas Shakti practice?", [], ["Ojas"]),
    ("sreepreethaji message", ["sri-preethaji"], []),
    ("साक्षी भाव क्या है", [], ["Witness Awareness"]),
    ("krishna ji ki shiksha", ["sri-krishnaji"], []),
    ("Give me a total surrender practice", [], ["Surrender"]),
]

# Queries that must link NOTHING — generic English, chit-chat, out-of-corpus,
# and known ambiguity traps. These pin the precision guard: bare generics
# (awareness, unity, surrender, grace) and bare "krishna"/"maya" stay out.
NEGATIVE_FIXTURES: list[str] = [
    "What is the capital of France?",
    "How are you today?",
    "I feel aware of my surroundings lately",
    "Tell me about quantum physics",
    "Stories of Krishna and Arjuna",
    "My friend Maya is coming over",
    "What time is it?",
    "I surrender my worries to the night",
    "Seek unity and peace within",
    "The master explained gravity",
]


def _expected_links() -> dict[tuple[str, str], set[str]]:
    expected: dict[tuple[str, str], set[str]] = {}
    for query, teachers, terms in POSITIVE_FIXTURES:
        expected[(query, "teachers")] = set(teachers)
        expected[(query, "terms")] = set(terms)
    for query in NEGATIVE_FIXTURES:
        expected[(query, "teachers")] = set()
        expected[(query, "terms")] = set()
    return expected


def test_linking_precision_on_fixtures():
    """Link-level precision must be 1.0: every emitted link was expected."""
    expected = _expected_links()
    true_pos = 0
    false_pos = 0
    for (query, field), want in expected.items():
        got = set(link_entities(query)[field])
        true_pos += len(got & want)
        false_pos += len(got - want)
    precision = true_pos / (true_pos + false_pos) if (true_pos + false_pos) else 1.0
    assert false_pos == 0, f"false-positive links emitted: precision={precision:.3f}"
    assert precision == 1.0


def test_linking_recall_on_fixtures():
    """Every expected link is emitted (no false negatives on fixtures)."""
    expected = _expected_links()
    missing = []
    for (query, field), want in expected.items():
        got = set(link_entities(query)[field])
        if not want <= got:
            missing.append((query, field, sorted(want - got)))
    assert missing == [], f"expected links missing: {missing}"


def test_teachers_restricted_to_licensed_okf_ids():
    """The teachers field only ever carries _okf_match-compatible ids."""
    for query, _, _ in POSITIVE_FIXTURES:
        for teacher in link_entities(query)["teachers"]:
            assert teacher in ("sri-preethaji", "sri-krishnaji"), teacher


def test_other_teachers_link_as_terms_not_teachers():
    """Recognized-but-unlicensed teachers must not enter the teacher filter."""
    links = link_entities("What does Sadhguru say about karma?")
    assert links["teachers"] == []
    assert "Sadhguru" in links["terms"]
    assert "Karma" in links["terms"]


def test_bare_krishna_is_not_a_teacher_mention():
    """Documented limitation: bare 'Krishna' is deity-ambiguous, stays out."""
    assert link_entities("Stories of Krishna")["teachers"] == []


def test_empty_query_links_nothing():
    assert link_entities("") == {"teachers": [], "terms": [], "tags": []}
    assert link_entities("   ")["teachers"] == []


def test_tags_mirror_terms_lowercased():
    """Tags are the knowledge_tags-ready lowercase forms of terms."""
    links = link_entities("Soul Sync meditation by Preethaji")
    assert links["tags"] == [t.lower() for t in links["terms"]]


def test_resolve_disabled_is_noop():
    """Default path: links traced, inputs returned unchanged."""
    tags = ["existing-tag"]
    links, eff_tags, eff_teacher = resolve_entity_links(
        "What did Preethaji teach about Soul Sync?", tags, "sri-preethaji", enabled=False
    )
    assert links["teachers"] == ["sri-preethaji"]
    assert "soul sync" in links["tags"]
    assert eff_tags == tags
    assert eff_teacher == "sri-preethaji"


def test_resolve_disabled_with_empty_inputs():
    links, eff_tags, eff_teacher = resolve_entity_links(
        "What is the capital of France?", [], None, enabled=False
    )
    assert links == {"teachers": [], "terms": [], "tags": []}
    assert eff_tags == []
    assert eff_teacher is None


def test_resolve_enabled_unions_tags_never_replaces():
    """Enabled path is additive-only: existing tags survive, links append."""
    _, eff_tags, _ = resolve_entity_links(
        "Soul Sync meditation", ["custom-tag"], None, enabled=True
    )
    assert eff_tags[0] == "custom-tag"
    assert "soul sync" in eff_tags
    assert "meditation" in eff_tags


def test_resolve_enabled_fills_teacher_only_when_unambiguous():
    _, _, single = resolve_entity_links("Preethaji on grace", [], None, enabled=True)
    assert single == "sri-preethaji"
    # Comparative question: both teachers -> no filter (keep both lanes).
    _, _, both = resolve_entity_links(
        "How do Preethaji and Krishnaji describe oneness?", [], None, enabled=True
    )
    assert both is None
    # Explicit teacher_id always wins over the link.
    _, _, kept = resolve_entity_links("Preethaji on grace", [], "sri-krishnaji", enabled=True)
    assert kept == "sri-krishnaji"


def test_resolve_enabled_tag_budget_is_capped():
    """Union growth is bounded: at most +5 tags beyond existing ones."""
    _, eff_tags, _ = resolve_entity_links(
        "karma moksha dharma mantra bhakti jnana kriya atma samsara",
        [],
        None,
        enabled=True,
    )
    assert len(eff_tags) <= 5


def test_extra_aliases_track_doctrine_synonyms_or_lexicon():
    """Audit trail: every hand-added alias is either a DOCTRINE_SYNONYMS
    alternate (query-expansion vocabulary) or a lexicon/verification-attested
    proper noun / transliteration variant (source noted in entity_linking)."""
    from rag.nodes.utils import DOCTRINE_SYNONYMS

    synonym_forms = {
        alt.casefold() for alternates in DOCTRINE_SYNONYMS.values() for alt in alternates
    }
    synonym_forms |= {key.casefold() for key in DOCTRINE_SYNONYMS}
    # Lexicon proper nouns (backend/data/doctrine_lexicon.json) + blessing
    # transliterations (backend/rag/nodes/verification.py fraud regex).
    attested_elsewhere = {"ojas", "humsa", "sohum", "turiya", "lokaa", "aashirvaad", "aashirvad"}
    untracked = [a for a in _R6_EXTRA_ALIASES if a not in synonym_forms | attested_elsewhere]
    assert untracked == [], f"aliases with no vocabulary source: {untracked}"


@pytest.mark.asyncio
async def test_retrieve_documents_entity_linking_noop(monkeypatch):
    """Retrieval-level no-op proof: with the gate off (default), the hook
    records links in the trace while retrieved documents are byte-identical
    to the Qdrant hits — live ranking behavior unchanged."""
    import logging
    from unittest.mock import AsyncMock, MagicMock

    from app.config import settings

    logging.basicConfig(level=logging.DEBUG)

    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {"dense": [0.1] * 1024, "sparse": {"1": 0.5}}
    mock_embedder.encode_batch.return_value = {
        "dense": [[0.1] * 1024],
        "sparse": [{"1": 0.5}],
    }
    mock_embedder.instruction = "Given a spiritual teaching, retrieve relevant passages: "

    qdrant_hit = {
        "text": "Found document teaching",
        "source_url": "url1",
        "title": "doc1",
        "score": 0.9,
    }
    mock_qdrant = MagicMock()
    mock_qdrant.search = MagicMock(return_value=[dict(qdrant_hit)])
    mock_qdrant.search_groups = MagicMock(return_value=[dict(qdrant_hit)])

    mock_lightrag = MagicMock()
    mock_lightrag.aquery = AsyncMock(return_value="LightRAG wisdom")

    import rag.nodes as nodes
    from rag.nodes import _services

    monkeypatch.setattr(_services, "_ollama", AsyncMock())
    monkeypatch.setattr(_services, "_embedder", mock_embedder)
    monkeypatch.setattr(_services, "_qdrant", mock_qdrant)
    monkeypatch.setattr(_services, "_lightrag", mock_lightrag)

    monkeypatch.setattr(settings, "rag_okf_injection_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(settings, "retrieval_score_delta_enabled", False)
    monkeypatch.setattr(settings, "rag_skip_retrieval_expansions", True)
    monkeypatch.setattr(settings, "kg_ontology_expansion_timeout", 0.05)
    # Gate OFF (the default): rag_entity_linking_enabled is absent from
    # app.config by design (read-only) — the retrieval hook reads it via a
    # getattr fallback defaulting to False. Absence here IS the default case.
    mock_container = MagicMock()
    mock_container.neo4j_driver = None
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    state = {
        "question": "What did Preethaji teach about Soul Sync?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": ["What did Preethaji teach about Soul Sync?"],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "FACTUAL",
    }
    res = await nodes.retrieve_documents(state)
    assert "error" not in res
    # Links observed in the trace ...
    trace_links = res["evaluation_trace"]["entity_links"]
    assert trace_links["teachers"] == ["sri-preethaji"]
    assert "soul sync" in trace_links["tags"]
    # ... while retrieval output is exactly the Qdrant hit (no-op).
    assert any(doc["text"] == "Found document teaching" for doc in res["documents"])
    for doc in res["documents"]:
        assert doc["source_url"] == "url1"
