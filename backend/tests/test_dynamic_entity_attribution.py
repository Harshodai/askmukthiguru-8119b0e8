"""Unit and integration tests for Dynamic Entity Attribution and Boundary Resolution (PROD-RET / ua46).

Validates:
1. Dynamic Entity Extraction: Any external teacher or tradition asked about directly
   is extracted without needing a static hardcoded deny-list.
2. Honest Domain Boundary Formulation: Unregistered entities yield transparent boundaries
   (0 citations, 0 hallucinations).
3. Comparative Queries: Inquiries comparing an in-domain registered guru with an external
   tradition are recognized as comparative, allowing in-domain retrieval rather than hard blocking.
4. Typo and prefix resilience: "Swami Vivekananda", "Father Bede Griffiths", "Master Eckhart", etc.
"""

import pytest
from services.guru_registry import (
    extract_target_authority,
    format_external_teacher_boundary,
    is_comparative_authority_query,
    requested_unregistered_teacher_or_tradition,
)


# ---------------------------------------------------------------------------
# 1. Zero-Shot Dynamic External Teacher Extraction (25+ Diverse Figures)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query,expected_entity",
    [
        ("What does Alan Watts teach about the illusion of the ego?", "Alan Watts"),
        ("How does Marcus Aurelius view adversity in Meditations?", "Marcus Aurelius"),
        ("According to Thich Nhat Hanh, what is mindful walking?", "Thich Nhat Hanh"),
        ("What did Ramana Maharshi say about who am I?", "Ramana Maharshi"),
        ("What does Byron Katie teach about questioning your thoughts?", "Byron Katie"),
        ("How does Eckhart Tolle explain the pain-body?", "Eckhart Tolle"),
        ("What does Nisargadatta Maharaj teach about I Am That?", "Nisargadatta Maharaj"),
        ("According to Epictetus, what is within our control?", "Epictetus"),
        ("How did Swami Vivekananda describe Raja Yoga?", "Vivekananda"),
        ("What does Paramahansa Yogananda say about Kriya Yoga?", "Paramahansa Yogananda"),
        ("What does Jiddu Krishnamurti say about the observer and observed?", "Jiddu Krishnamurti"),
        ("What does Sadhguru teach about Shambhavi Mahamudra?", "Sadhguru"),
        ("How does Rumi describe the longing of the soul?", "Rumi"),
        ("What is Lao Tzu's perspective on Wu Wei?", "Lao Tzu"),
        ("According to Meister Eckhart, what is divine detachment?", "Meister Eckhart"),
        ("What does Seneca write about the shortness of life?", "Seneca"),
        ("How does Mooji explain effortless awareness?", "Mooji"),
        ("What does Papaji teach about silence?", "Papaji"),
        ("What did Anandamayi Ma teach about divine joy?", "Anandamayi Ma"),
        ("According to Neem Karoli Baba, how should one serve?", "Neem Karoli Baba"),
        ("What does Deepak Chopra teach about the seven spiritual laws?", "Deepak Chopra"),
        ("How does Gurdjieff explain self-remembering?", "Gurdjieff"),
        ("What does Ram Dass say about being here now?", "Ram Dass"),
        ("What does Pema Chodron teach about groundlessness?", "Pema Chodron"),
        ("How does Joseph Campbell describe the hero's journey?", "Joseph Campbell"),
        ("What does Sri Sri Ravi Shankar teach about breath?", "Ravi Shankar"),
    ],
)
def test_zero_shot_external_teacher_extraction(query, expected_entity):
    """External figures must be dynamically extracted as unregistered authorities."""
    auth = extract_target_authority(query)
    assert auth is not None, f"Failed to extract authority from: {query}"
    assert auth["is_registered"] is False
    assert expected_entity.lower() in auth["target"].lower()

    unreg = requested_unregistered_teacher_or_tradition(query)
    assert unreg is not None
    assert expected_entity.lower() in unreg.lower()


# ---------------------------------------------------------------------------
# 2. In-Domain Registered Teachers Are Never Flagged as External
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "What does Sri Preethaji teach about moving from fear to connection?",
        "How does Sri Krishnaji explain the four sacred secrets?",
        "What did Krishnaji say about the nature of intelligence?",
        "According to Preethaji, how does the beautiful state arise?",
        "What does Sri Krishnaji teach about awakening and inner peace?",
    ],
)
def test_in_domain_teachers_are_registered_and_not_unregistered(query):
    """Registered in-domain gurus must be recognized as registered."""
    auth = extract_target_authority(query)
    assert auth is not None
    assert auth["is_registered"] is True
    assert auth["guru_id"] is not None

    unreg = requested_unregistered_teacher_or_tradition(query)
    assert unreg is None


# ---------------------------------------------------------------------------
# 3. Comparative Queries (In-Domain vs External)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "How does Sri Preethaji differ from Thich Nhat Hanh on walking meditation?",
        "Compare Sri Krishnaji and Alan Watts on the ego",
        "What does Preethaji teach about fear compared to Eckhart Tolle?",
        "Sri Krishnaji versus Jiddu Krishnamurti on the observer",
    ],
)
def test_comparative_queries_allow_in_domain_retrieval(query):
    """Inquiries comparing registered gurus with external authorities
    must be flagged as comparative, preventing blanket abstention.
    """
    is_comp, in_gurus, ext_auths = is_comparative_authority_query(query)
    assert is_comp is True
    assert len(in_gurus) >= 1
    assert len(ext_auths) >= 1

    # When allow_comparative=True, it does not treat it as a hard unanswerable block
    unreg = requested_unregistered_teacher_or_tradition(query, allow_comparative=True)
    assert unreg is None


# ---------------------------------------------------------------------------
# 4. Transparent Dynamic Boundary Formulation
# ---------------------------------------------------------------------------

def test_dynamic_boundary_formatting():
    boundary = format_external_teacher_boundary("Alan Watts", "the illusion of ego")
    assert "Alan Watts" in boundary
    assert "the illusion of ego" in boundary
    assert "dedicated exclusively" in boundary
    assert "🙏" in boundary
