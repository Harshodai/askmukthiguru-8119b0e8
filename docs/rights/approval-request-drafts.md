# Draft Approval-Request Messages

**SUPERSEDED 2026-09-23.** Project owner (Harshodai) states these approvals — Ekam/O&O Academy, Times Now, and the Four Sacred Secrets rights basis — were already secured directly, outside this drafting process. See `CONTENT-RIGHTS.md` and `docs/rights/source-register.md` for the recorded confirmation. These drafts are kept below for provenance only; **do not send them**, they're no longer needed. Not independently verified by any agent (N9) — recorded as the owner's statement.

**These are drafts only. No agent has sent, or should send, any of these.**
A human must review, fill in the `[bracketed]` gaps, and send them.

---

## 1. Ekam / O&O Academy (covers "Sri Preethaji & Sri Krishnaji" + "Ekam / O&O
Academy" channels, ~2,928 of the ~14,033 indexed points by direct channel
attribution, plus an unknown share of the ~7,300 "Unknown Channel"/"Unknown"
points that are presumed but not verified to be the same source)

> Subject: Content usage permission request — AskMukthiGuru AI project
>
> Dear [Ekam / O&O Academy contact name],
>
> I'm reaching out regarding AskMukthiGuru, an AI-based spiritual guidance
> application built on the public teachings of Sri Preethaji & Sri Krishnaji.
> The project currently uses transcripts and derived text from publicly
> posted YouTube videos on [channel name/URL] to answer seekers' questions,
> always with attribution back to the source video.
>
> I'd like to request written permission to continue using this content in
> this way, and to understand what rights basis (if any) already covers it —
> for example, whether the channel's own terms already permit this kind of
> use, or whether a separate license/agreement is needed.
>
> Specifically I'd appreciate confirmation on:
> 1. Whether AskMukthiGuru may use transcripts of [channel name]'s public
>    YouTube videos to answer user questions, with source attribution.
> 2. Whether there are specific videos, playlists, or types of content we
>    should exclude.
> 3. Whether "The Four Sacred Secrets" book (Sri Preethaji & Sri Krishnaji,
>    Sounds True) may be used in the same way, separately from the YouTube
>    content — see item 3 below for that book specifically.
>
> Happy to share the full list of video URLs currently in use, or a technical
> walkthrough of how the content is retrieved and cited, if helpful.
>
> Thank you,
> [name / org]

---

## 2. Times Now (broadcaster — 353 points, news coverage segment(s) featuring
the gurus, not the org's own upload)

> Subject: Content usage permission request — AskMukthiGuru AI project
>
> Dear Times Now [rights/legal contact],
>
> AskMukthiGuru, an AI spiritual-guidance application, has indexed a
> transcript of Times Now's news coverage of Sri Preethaji & Sri Krishnaji
> (specifically: "[video title]", [YouTube URL]) as part of a knowledge base
> used to answer user questions, with source attribution back to the video.
>
> I'd like to confirm whether this use is permitted, and if not, request
> permission or guidance on what would be required — or whether we should
> remove this content instead.
>
> [video URL(s) to be filled in by whoever sends this]
>
> Thank you,
> [name / org]

---

## 3. Sri Preethaji & Sri Krishnaji / Sounds True — "The Four Sacred Secrets"
book (1,199 points, currently live in production despite being flagged
unconfirmed and believed purged — see `CONTENT-RIGHTS.md` and
`docs/rights/source-register.md`)

> Subject: Urgent — content usage clarification, "The Four Sacred Secrets"
>
> Dear [Ekam Science Foundation / Sounds True rights contact],
>
> AskMukthiGuru, an AI spiritual-guidance application built on Sri Preethaji &
> Sri Krishnaji's teachings, ingested excerpts of "The Four Sacred Secrets"
> (Sounds True) into its knowledge base. We removed the original source file
> from our code repository on 2026-08-01 pending rights confirmation, but a
> re-ingestion under a different source reference (an Amazon product page
> URL) was not caught by that removal and is still present in our production
> database as of 2026-09-22.
>
> We are not currently serving this content while we sort out the rights
> question (or: [state actual current status honestly once a human decides
> what to do about the live re-ingestion — this draft does not presume an
> outcome]).
>
> Could you confirm:
> 1. What rights basis, if any, would permit an AI application to retrieve
>    and quote excerpts of this book in response to user questions, with
>    attribution?
> 2. Whether a licensing arrangement already exists between Sounds True and
>    Ekam / O&O Academy that would cover this, or whether a new agreement
>    is needed.
>
> Thank you,
> [name / org]

---

## Notes for whoever sends these

- Fill in every `[bracketed]` placeholder — especially real contact names,
  exact video/channel URLs, and the current live-serving status of item 3
  before sending it (do not send item 3's draft claiming content is "not
  currently serving" unless that is actually true at send time — check
  `settings.serve_only_registered_sources` and whether the blocklist fix in
  `services/qdrant/source_policy.py` has been deployed).
- None of these have been sent. No agent should send them.
