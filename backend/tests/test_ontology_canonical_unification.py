"""
Test ontology canonical unification across query, ingestion, and domain layers.
Verifies identical case-insensitive normalization and canonical entity resolution.
"""

import pytest
from domain.spiritual_ontology import (
    canonical_entity_id as domain_canonical_entity_id,
    normalize_entity_name as domain_normalize_entity_name,
    CANONICAL_ENTITY_ALIASES,
)
from services.spiritual_ontology import (
    canonical_entity_id as service_canonical_entity_id,
    normalize_entity_name as service_normalize_entity_name,
)
from rag.nodes.utils import (
    canonical_entity_id as rag_canonical_entity_id,
    normalize_entity_name as rag_normalize_entity_name,
    DOCTRINE_SYNONYMS,
)


REQUIRED_CORE_ENTITIES = {
    "beautiful state": "Beautiful State",
    "suffering state": "Suffering State",
    "four sacred secrets": "Four Sacred Secrets",
    "soul sync": "Soul Sync",
    "deeksha": "Deeksha",
    "ekam": "Ekam",
    "serene mind": "Serene Mind",
    "aham": "Aham",
}


@pytest.mark.parametrize("input_name,expected_canonical", REQUIRED_CORE_ENTITIES.items())
def test_canonical_entity_id_required_entities_lowercase(input_name, expected_canonical):
    """Verify all 8 required core entities resolve to exact canonical IDs."""
    assert domain_canonical_entity_id(input_name) == expected_canonical
    assert service_canonical_entity_id(input_name) == expected_canonical
    assert rag_canonical_entity_id(input_name) == expected_canonical


@pytest.mark.parametrize("input_name,expected_canonical", REQUIRED_CORE_ENTITIES.items())
def test_canonical_entity_id_case_insensitivity(input_name, expected_canonical):
    """Verify uppercase, titlecase, and mixed case strings resolve to canonical entity."""
    assert domain_canonical_entity_id(input_name.upper()) == expected_canonical
    assert domain_canonical_entity_id(input_name.title()) == expected_canonical
    assert service_canonical_entity_id(input_name.upper()) == expected_canonical
    assert rag_canonical_entity_id(input_name.upper()) == expected_canonical

    # Mixed case
    mixed = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(input_name))
    assert domain_canonical_entity_id(mixed) == expected_canonical
    assert service_canonical_entity_id(mixed) == expected_canonical
    assert rag_canonical_entity_id(mixed) == expected_canonical


@pytest.mark.parametrize("input_name,expected_canonical", REQUIRED_CORE_ENTITIES.items())
def test_canonical_entity_id_whitespace_normalization(input_name, expected_canonical):
    """Verify extra whitespace and inner multi-spaces are cleanly normalized."""
    padded = f"   {input_name.replace(' ', '   ')}   "
    assert domain_canonical_entity_id(padded) == expected_canonical
    assert service_canonical_entity_id(padded) == expected_canonical
    assert rag_canonical_entity_id(padded) == expected_canonical


def test_canonical_entity_aliases_coverage():
    """Verify aliases and variants for core entities resolve properly."""
    variants = {
        # Beautiful state variants
        "the beautiful state": "Beautiful State",
        "blissful state": "Beautiful State",
        "state of bliss": "Beautiful State",
        "beautiful_state": "Beautiful State",
        # Suffering state variants
        "the suffering state": "Suffering State",
        "state of suffering": "Suffering State",
        "painful state": "Suffering State",
        # Four Sacred Secrets variants
        "4 sacred secrets": "Four Sacred Secrets",
        "the four sacred secrets": "Four Sacred Secrets",
        "sacred secrets": "Four Sacred Secrets",
        # Soul Sync variants
        "soul synchronization": "Soul Sync",
        "soul sync meditation": "Soul Sync",
        # Deeksha variants
        "diksha": "Deeksha",
        "oneness blessing": "Deeksha",
        "divine blessing": "Deeksha",
        # Ekam variants
        "ekam world": "Ekam",
        "world centre for enlightenment": "Ekam",
        # Serene Mind variants
        "serene mind practice": "Serene Mind",
        "serene mind meditation": "Serene Mind",
        # Aham variants
        "ahamkara": "Aham",
        "ahamkar": "Aham",
        "i-ness": "Aham",
    }
    for alias, expected in variants.items():
        assert domain_canonical_entity_id(alias) == expected
        assert service_canonical_entity_id(alias) == expected
        assert rag_canonical_entity_id(alias) == expected


def test_honorific_stripping():
    """Verify honorific prefixes and suffixes are cleanly resolved to canonical IDs."""
    teacher_variants = {
        "Sri Preethaji": "Sri Preethaji",
        "Guru Preethaji": "Sri Preethaji",
        "Preethaji": "Sri Preethaji",
        "sri preethaji": "Sri Preethaji",
        "Sri Krishnaji": "Sri Krishnaji",
        "Guruji Krishnaji": "Sri Krishnaji",
        "Krishnaji": "Sri Krishnaji",
        "Swami Preethaji": "Sri Preethaji",
    }
    for variant, expected in teacher_variants.items():
        assert domain_canonical_entity_id(variant) == expected
        assert service_canonical_entity_id(variant) == expected
        assert rag_canonical_entity_id(variant) == expected


def test_unmapped_entity_fallback():
    """Verify unmapped concepts retain normalized form without crashing."""
    unmapped = "  unmapped custom concept   "
    assert domain_canonical_entity_id(unmapped) == "unmapped custom concept"
    assert service_canonical_entity_id(unmapped) == "unmapped custom concept"
    assert rag_canonical_entity_id(unmapped) == "unmapped custom concept"

    empty = ""
    assert domain_canonical_entity_id(empty) == ""
    assert service_canonical_entity_id(empty) == ""
    assert rag_canonical_entity_id(empty) == ""


def test_layer_equivalence_parity():
    """Verify complete parity across domain, service, and rag layers."""
    test_suite = [
        "beautiful state",
        "BEAUTIFUL STATE",
        "suffering state",
        "four sacred secrets",
        "soul sync",
        "deeksha",
        "ekam",
        "serene mind",
        "aham",
        "Sri Preethaji",
        "O&O Academy",
        "Bhagavad Gita",
        "random concept",
    ]
    for term in test_suite:
        d_res = domain_canonical_entity_id(term)
        s_res = service_canonical_entity_id(term)
        r_res = rag_canonical_entity_id(term)
        assert d_res == s_res == r_res, f"Drift detected for '{term}': domain={d_res}, service={s_res}, rag={r_res}"


def test_doctrine_synonyms_alignment_with_canonical_id():
    """Verify DOCTRINE_SYNONYMS keys align with canonical_entity_id mappings."""
    for required_key in REQUIRED_CORE_ENTITIES:
        assert required_key in DOCTRINE_SYNONYMS, f"Missing {required_key} in DOCTRINE_SYNONYMS"
        # Each primary entry in DOCTRINE_SYNONYMS should resolve to its canonical entity
        canon = domain_canonical_entity_id(required_key)
        assert canon == REQUIRED_CORE_ENTITIES[required_key]
