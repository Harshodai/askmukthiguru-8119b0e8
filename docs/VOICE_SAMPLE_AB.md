# Voice sample A/B — person and attribution (DECIDED)

**Status: DECIDED 2026-09-16 — Option A, third person with attributed quotes.**

## The decision and, more importantly, the reason

> "this product is also a disciple of the gurus" — product owner

That sentence is the contract, and it settles more than this one question. A
disciple **transmits** a teaching and **attributes** it. A disciple does not
speak *as* the teacher. So the assistant speaks about Sri Preethaji and Sri
Krishnaji in the third person, and quotes their own words verbatim, with a
speaker label, when the retrieved teaching carries them.

Use this principle to resolve any future ambiguity about voice: ask whether a
disciple would say it that way.

Two things worth recording, because they make the choice safer rather than
merely different:

1. **Option A cannot impersonate, by construction.** There is no prompt path by
   which it produces an unattributed first-person teaching sentence. That
   matters most in the case this product is actually built for — the Gurus and
   their senior disciples reading the output and judging whether it
   misrepresents them. A misattributed sentence is the worst failure this
   system can produce, worse than a refusal.
2. **Option B never really became first person anyway.** Both samples below
   open with "Sri Preethaji and Sri Krishnaji teach that…". The instruction did
   not overcome the grounding contract, which is itself evidence that the
   attribution habit is load-bearing rather than cosmetic.

The metric could not separate the two (4.22 vs 5.06), which is the correct
result: person is a doctrinal question, not a measurable-quality one. It was
right to decide it from the text rather than from the number.

## What changed as a result

`services/guru_brain/guru_brain_service.py` was the only layer disagreeing — it
forbade speaker labels and forbade third-person attribution, i.e. exactly the
strings that `rag/prompts/system.py` ("How you speak" and `GURU_VOICE_RULE`)
and `services/guru_voice_langhanam.py` rule 2 mandate. Those four rules are
deleted. Shipping both instructions in one prompt was strictly worse than
shipping neither.

The decorative `$Y_{win}$`/`$Y_{lose}$` DPO notation went with them: nothing in
this system is trained — no preference pairs, no reward model, no reference
model, no gradient — so the notation described nothing the code does and spent
prompt tokens teaching the model LaTeX it has no use for.

---

*The original sample that informed the decision is preserved below.*

You asked to decide this from a real sample rather than from a description, so
this document is the sample. Both answers below are real model output to the
same golden question, with the same retrieved context, the same teacher profile
(`preethaji_krishnaji`), and the same new register block. The ONLY difference is the
person/attribution instruction appended at the end.

## The conflict this resolves

Three places in the codebase currently agree, and one disagrees:

| Where | Says |
| :-- | :-- |
| `rag/prompts/system.py` ("How you speak") | Third person about the founders; their first person preserved **in quotation**, attributed |
| `rag/prompts/system.py` `GURU_VOICE_RULE` | Same — speaker-labelled quotes |
| `services/guru_voice_langhanam.py` rule 2 | Same — keep their "I", attribute it |
| `services/guru_brain/guru_brain_service.py:316-327` | **Forbids** exactly those third-person strings |

Whichever you choose, the loser gets deleted so the contract stops
contradicting itself.

## The question

**Option A — third person, with attributed quotes.** The assistant is a
knowledgeable friend of the tradition who speaks *about* Sri Preethaji and Sri
Krishnaji, and quotes them directly when the retrieved teaching carries their
own words.

**Option B — first person, direct.** The assistant speaks *as* the teaching
voice, in first person where the context supports it.

The grounding invariant is identical either way: neither option may invent a
first-person sentence the retrieved context does not contain.

---

## Option A — third person with attribution

Guru Voice Distance **4.22** *(verbatim guru speech 0.37 · LLM summary prose 1.64 · old-prompt baseline median 8.52)*

> The First Sacred Secret, **Spiritual Vision for Life**, is the foundation of all visions. Sri Preethaji and Sri Krishnaji teach that discovering your life’s purpose begins with aligning with a spiritual vision. This vision is not about external achievements or material success but about connecting with the deeper truth of who you are and why you are here.
> 
> Many people believe that happiness comes from getting everything in life "right" first — the perfect job, relationships, or circumstances. But the teachings invite you to shift this perspective. Instead of waiting for external conditions to bring joy, you are encouraged to cultivate inner joy first. When you are joyful, everything else aligns naturally.
> 
> Spiritual vision is the moth that draws you toward the light of your true purpose. It is not something you create but something you discover within yourself. When you connect with this vision, it becomes your guiding force, helping you navigate life with clarity and intention. As Sri Krishnaji often shares, "A person should first become joyful, and then everything will happen."
> 
> To begin this journey, ask yourself: What brings me deep joy? What feels aligned with my inner truth? When you answer these questions sincerely, you take the first step toward uncovering your spiritual vision and living a life of purpose.

---

## Option B — first person, direct

Guru Voice Distance **5.06**

> The First Sacred Secret, **Spiritual Vision**, is the foundation of a purposeful and abundant life. Sri Preethaji and Sri Krishnaji teach that your spiritual vision is not just a goal or a dream; it is the guiding light that aligns your actions with your deepest truth. It is the moth drawn to the flame, the inner pull toward something greater than yourself.
> 
> Many people believe that happiness comes from achieving external success — wealth, relationships, or status. But the teachings reveal a profound shift: joy must come first. When you cultivate joy within, your spiritual vision naturally emerges, and everything else flows from there. This vision becomes your purpose, the force that drives you to work hard and move forward, even in times of confusion or challenge.
> 
> Your spiritual vision is not about what you want to *have*; it is about who you want to *be* and how you want to contribute to the world. It is the first step toward opening to a life of meaning and connection. When you align with this vision, you step into the field of abundance, where your destiny unfolds with grace and ease.

---

## What I observed, without choosing for you

- **The metric does not separate them** (4.22 vs 5.06). Both sit far
  better than the old-prompt baseline (median 8.52) but worse than the best
  prose results elsewhere in this run (0.66). Person is not what drives the
  "sounds like AI" signal — formatting is. **This is a taste and theology
  decision, not a measurable-quality one, which is exactly why it is yours.**
- **Option B did not actually become first-person.** Asked to speak as the
  teaching voice, the model still wrote "Sri Preethaji and Sri Krishnaji
  teach...". Worth knowing before you pick B: it may need stronger instruction,
  and stronger instruction on identity is the highest-risk kind of prompt change
  in a zero-hallucination system.
- **Both samples still emit `**bold**`** despite the new rule forbidding it.
  Prompt adherence here is partial; see "Known gaps" in the report.
- **The risk profile differs.** A is safe by construction — it cannot
  impersonate. B carries a real hazard: a model speaking as the Guru in first
  person, one hallucination away from putting invented words in a living
  teacher's mouth. The repo's existing `GURU_VOICE_RULE` chose A for that
  reason.

## To decide

Tell me **A** or **B**. I will then make the four locations agree and delete the
contradicting rule in `guru_brain_service.py:316-327`.

---
*Generated 2026-09-15 · question: "Explain the First Sacred Secret: Spiritual Vision for Life."*
