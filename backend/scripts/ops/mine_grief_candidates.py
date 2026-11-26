#!/usr/bin/env python3
"""mine_grief_candidates.py

Mines and formats standalone teachings on grief, loss, mourning, and sorrow
from Sri Preethaji & Sri Krishnaji transcripts that are completely free of
self-harm and suicidal despair markers.

Produces:
  - audits/evidence/grief_standalone_candidates.json
  - audits/evidence/grief_standalone_candidates.md
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

# Self-harm / suicidal despair regex matching runtime safety filter
_CLIP_MENTIONS_SELF_HARM = re.compile(
    r"\b(?:self[\s-]*harm|suicid\w*|kill(?:ing)?\s+(?:my|your|him|her|them)self"
    r"|end(?:ing)?\s+(?:my|your|his|her|their|one'?s)\s+(?:own\s+)?life|take\s+(?:my|your|his|her|their|one'?s)\s+own\s+life"
    r"|thinking\s+of\s+dying|want(?:ing)?\s+to\s+die)\b",
    re.IGNORECASE,
)

CANDIDATES = [
    {
        "id": "grief_cand_01",
        "video_id": "Oc5ar2g2rnI",
        "title": "Life After Death | Evolution Series 72",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=Oc5ar2g2rnI",
        "start_s": 85.0,
        "end_s": 160.0,
        "audio_archive_status": "archived",
        "category": "Life After Death & Sacred Interconnectedness",
        "topic": "Death as a sacred transition in an unending stream of consciousness",
        "verbatim_quote": (
            "If you looked at the perception of life as an unending stream of consciousness "
            "without birth, without death, your current experience of life itself becomes very sacred. "
            "The people you meet in your life, you know are people with whom you have shared lifetimes of connection. "
            "That you know you have a shared journey, a shared mission to accomplish on this planet. "
            "You have a shared evolution to achieve in this lifetime. This brings a greater significance "
            "to human relationship itself. You are not terrified of death or old age because you know "
            "you have been old many times before and that death is only a transition from one phase to another."
        ),
        "clinical_safeguard_notes": (
            "Screens clean against _CLIP_MENTIONS_SELF_HARM. Provides spiritual perspective on mortality, "
            "honoring connections across lifetimes, without morbid ideation."
        ),
    },
    {
        "id": "grief_cand_02",
        "video_id": "Oc5ar2g2rnI",
        "title": "Life After Death | Evolution Series 72",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=Oc5ar2g2rnI",
        "start_s": 260.0,
        "end_s": 320.0,
        "audio_archive_status": "archived",
        "category": "Releasing the Departed & Family Peace",
        "topic": "Releasing departed ancestors into light and experiencing emotional liberation",
        "verbatim_quote": (
            "One of the gifts that is offered is releasing the departed. Thousands today have a "
            "first-hand experience of releasing the departed. They experience an instant liberation "
            "and instant emotional release when their departed move into the light in a state of peace. "
            "Long-standing obstacles give way and the dissolution of health problems happens in the family "
            "when the departed move into the light. It is a stuck energy and a restless energy that has been cleared."
        ),
        "clinical_safeguard_notes": (
            "Addresses feelings of stuck emotional grief and unresolved guilt regarding departed loved ones. "
            "Offers positive psychological release and familial healing."
        ),
    },
    {
        "id": "grief_cand_03",
        "video_id": "Oc5ar2g2rnI",
        "title": "Life After Death | Evolution Series 72",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=Oc5ar2g2rnI",
        "start_s": 345.0,
        "end_s": 416.0,
        "audio_archive_status": "archived",
        "category": "Fearlessness in the Face of Mortality",
        "topic": "Mahaprasthana: Living fully without regret and loving completely without reserve",
        "verbatim_quote": (
            "That is why death is called Mahaprasthana, which means the commencement of a great journey. "
            "Life and afterlife are fundamentally like dreams you wake up from and come into waking. "
            "Only which of this is waking and which of this is the dreaming is the question. "
            "The only way you can be fearless about death is when you live life fully without regret. "
            "The only way you will be ready to embrace death when it comes knocking is when you love completely without reserve."
        ),
        "clinical_safeguard_notes": (
            "Inspirational spiritual discourse redirecting sorrow toward unconditional love and present living."
        ),
    },
    {
        "id": "grief_cand_04",
        "video_id": "bF6kr28QHJc",
        "title": "How to know when it's time to let go",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=bF6kr28QHJc",
        "start_s": 143.18,
        "end_s": 172.50,
        "audio_archive_status": "archived",
        "category": "Navigating Suffering from Loss & Disappointment",
        "topic": "Awakening a grander state of consciousness when facing the death of a parent or loss of love",
        "verbatim_quote": (
            "When disaster occurs or when life slowly and gradually turns bitter and disappointing, "
            "because of the death of a parent, the loss of love, the gradual dissolution of a dream, "
            "we experience the same suffering that humans have endured since the beginning of time. "
            "But despite all our technological advancements, modern society has not given us the tools "
            "we need to emerge from these crisis with a grander state of consciousness we need for the next chapter."
        ),
        "clinical_safeguard_notes": (
            "Directly names the death of a parent and loss of love, framing the pain as universal human experience "
            "and orienting the seeker toward inner growth and resilience."
        ),
    },
    {
        "id": "grief_cand_05",
        "video_id": "odXq5g-Y7gM",
        "title": "Spiritual hacks to heal heartache and depression",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=odXq5g-Y7gM",
        "start_s": 42.0,
        "end_s": 88.0,
        "audio_archive_status": "archived",
        "category": "Healing Heartache & Relieving Grief",
        "topic": "Physical presence, connection, and sending healing love to relieve heartache",
        "verbatim_quote": (
            "Gentle and loving physical touch while you actually hold an intention for the other to be happy "
            "can actually relieve a heartache and heal the other. A healing love flows from your body to the other "
            "when you are in a Beautiful State of love and hold a heartfelt wish for the well-being of the other. "
            "Your body actually emanates healing influence on the other."
        ),
        "clinical_safeguard_notes": (
            "Practical relational guidance for supporters or seekers experiencing emotional heartbreak or grief."
        ),
    },
    {
        "id": "grief_cand_06",
        "video_id": "DmzZPgTh7_M",
        "title": "How to become free of sorrow flowing from the past",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=DmzZPgTh7_M",
        "start_s": 764.22,
        "end_s": 835.0,
        "audio_archive_status": "archived",
        "category": "Freedom from Generational and Chronic Sorrow",
        "topic": "Recognizing sorrow that flows through memories and ancestry, and freeing oneself from it",
        "verbatim_quote": (
            "So, the past is a part of you - the good things of the past, the bad things of the past. "
            "But for some reason, if you are constantly feeling sorrow or sadness, then it need not be from "
            "the past that's happening to you, from this life. Your past is just not from the time you were born. "
            "Your past moves beyond that... Now, is it possible to become free of that sorrow that is flowing "
            "from the past? We don't know from where it's exactly flowing, but from wherever it is flowing, "
            "is it possible to become free of it? The answer is yes. It is possible to become free of this past today."
        ),
        "clinical_safeguard_notes": (
            "Validates chronic sorrow while giving hope and affirmation of liberation without despair."
        ),
    },
    {
        "id": "grief_cand_07",
        "video_id": "XzS56RqIxeE",
        "title": "Awakening to Compassion and the Oneness of Human Experience",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "youtube_url": "https://www.youtube.com/watch?v=XzS56RqIxeE",
        "start_s": 435.0,
        "end_s": 472.0,
        "audio_archive_status": "archived",
        "category": "Shared Oneness in Grief & Compassion",
        "topic": "Recognizing that human sorrow is shared, dissolving isolation in times of pain",
        "verbatim_quote": (
            "My experience of fear and your experience of fear is not different. It is not separate. "
            "My experience of sorrow and your experience of sorrow is just the same. If we move away "
            "from holding on to the superficial differences that we experience and move into the oneness "
            "of human experience, then we will awaken to compassion."
        ),
        "clinical_safeguard_notes": (
            "Counteracts the profound isolation felt during grief by highlighting universal human connection."
        ),
    },
]


def main() -> None:
    output_dir = Path("audits/evidence")
    output_dir.mkdir(parents=True, exist_ok=True)

    verified_candidates = []
    for cand in CANDIDATES:
        quote = cand["verbatim_quote"]
        match = _CLIP_MENTIONS_SELF_HARM.search(quote)
        assert match is None, f"Self-harm detected in {cand['id']}: {match}"
        verified_candidates.append(
            {
                **cand,
                "self_harm_check_passed": True,
                "screened_at": datetime.now(UTC).isoformat(),
            }
        )

    json_path = output_dir / "grief_standalone_candidates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": "1.0",
                "generated_at": datetime.now(UTC).isoformat(),
                "total_candidates": len(verified_candidates),
                "screening_policy": "STRICT_EXCLUSION_OF_SELF_HARM",
                "regex_pattern": _CLIP_MENTIONS_SELF_HARM.pattern,
                "candidates": verified_candidates,
            },
            f,
            indent=2,
        )
    print(f"Wrote {len(verified_candidates)} candidates to {json_path}")

    # Write Markdown review sheet
    md_path = output_dir / "grief_standalone_candidates.md"
    lines = [
        "# Standalone Grief & Loss Teachings: Candidate Review Packet",
        "",
        f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d')}  ",
        "**Status:** PROPOSED FOR OWNER & CLINICIAN REVIEW  ",
        "**Corpus Gap Reference:** `docs/plans/CORPUS_GAP_INGESTION_PLAN_2026_11_20.md`  ",
        "**Safety Invariant:** All candidates verified clean against `_CLIP_MENTIONS_SELF_HARM` "
        "(zero suicide/self-harm triggers; safe for non-crisis bereavement queries).",
        "",
        "---",
        "",
        "## Summary of Candidates",
        "",
        "| ID | Video ID | Category | Start - End | Title |",
        "|---|---|---|---|---|",
    ]

    for c in verified_candidates:
        lines.append(
            f"| `{c['id']}` | `{c['video_id']}` | {c['category']} | "
            f"{c['start_s']:.1f}s - {c['end_s']:.1f}s | [{c['title']}]({c['youtube_url']}?t={int(c['start_s'])}) |"
        )

    lines.extend(["", "---", "", "## Detailed Candidate Cards", ""])

    for c in verified_candidates:
        lines.extend(
            [
                f"### {c['id']}: {c['title']} (`{c['video_id']}`)",
                f"- **Topic:** {c['topic']}",
                f"- **Speaker:** {c['speaker']}",
                f"- **Timestamps:** {c['start_s']:.1f}s – {c['end_s']:.1f}s (duration: {c['end_s'] - c['start_s']:.1f}s)",
                f"- **YouTube Link:** [{c['youtube_url']}?t={int(c['start_s'])}]({c['youtube_url']}?t={int(c['start_s'])})",
                f"- **Audio Archive Status:** `{c['audio_archive_status']}`",
                f"- **Clinical Safeguard Assessment:** {c['clinical_safeguard_notes']}",
                "",
                "> **Verbatim Clip Text:**  ",
                f'> "{c["verbatim_quote"]}"',
                "",
                "**Reviewer Action:** [ ] APPROVE for v13 shadow index  |  [ ] REJECT  |  [ ] ADJUST WINDOW",
                "",
                "---",
                "",
            ]
        )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote human review packet to {md_path}")


if __name__ == "__main__":
    main()
