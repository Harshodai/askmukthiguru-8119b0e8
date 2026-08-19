"""P1-AI-9: distress prompt must source helplines from the registry and
never promise an immediate guided meditation in SEVERE distress.

The SEVERE/CRISIS blocks of `rag.prompts.system.DISTRESS_PROMPT` previously
hardcoded helpline numbers (a 4th copy of the data — drift risk) and promised
"guide you through a calming Serene Mind meditation" even though
`MeditationGenStage` skips meditation generation for SEVERE distress (a
broken promise to a distressed user). These tests pin the remediation:
the rendered prompt carries exactly the registry values, the source contains
no hardcoded phone numbers, and the SEVERE offer is a soft, non-committal one.
"""

from __future__ import annotations

import re

from rag.prompts.system import DISTRESS_PROMPT, build_distress_prompt
from services.crisis_helplines import _FALLBACK_HELPLINES, format_helplines_block, get_helplines


def test_helpline_from_registry():
    """Rendered distress prompt contains the registry's helpline values."""
    rendered = build_distress_prompt()

    assert "{helplines_block}" not in rendered, "placeholder was not substituted"

    helplines = get_helplines() or _FALLBACK_HELPLINES
    for helpline in helplines:
        assert helpline.contact in rendered, (
            f"registry contact {helpline.contact!r} missing from rendered prompt"
        )

    rendered_block = format_helplines_block(style="bullet", intro="")
    assert rendered_block in rendered, "registry-formatted block must appear verbatim"


def test_no_hardcoded_helplines():
    """No phone-number-like literal survives in the prompt source or output.

    The rendered prompt legitimately contains the registry contacts, so every
    phone-like token found must trace back to a registry entry; the module
    constant itself must be free of any phone-like literal.
    """
    rendered = build_distress_prompt()

    phone_like = re.compile(r"(?<!\w)(?:\d[\d\s-]{6,}\d|\d{3}-\d{3,}|\d{3,4}-\d{6,})(?!\w)")
    contacts = " ".join(h.contact for h in get_helplines())
    for match in phone_like.finditer(rendered):
        token = match.group(0)
        assert token in contacts, (
            f"phone-like token {token!r} in rendered prompt is not a registry contact"
        )

    source = DISTRESS_PROMPT
    for token in ("9152987821", "9820466726", "+91 9999 666 555", "044-24640050", "741741", "988"):
        assert token not in source, (
            f"old hardcoded helpline token {token!r} still in DISTRESS_PROMPT"
        )

    assert not phone_like.search(source), (
        "DISTRESS_PROMPT source still contains a hardcoded phone-like number"
    )


def test_severe_no_meditation_promise():
    """SEVERE block offers a practice softly, never an immediate guided meditation."""
    rendered = build_distress_prompt()

    assert "guide you through a calming Serene Mind meditation" not in rendered
    assert "I would like to guide you through" not in rendered

    soft_offer = "When you're ready, I can share a calming practice with you."
    assert soft_offer in rendered, "SEVERE block must contain the soft offer"
