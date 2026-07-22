# AskMukthiGuru — USER Demo Video Script (v2)
Target length: 75–90 seconds | 1920x1080 | Captions ON, animated in during edit (no live voiceover — see note below)
Recording target: **production** — https://askmukthiguru.lovable.app

Ground truth re-verified against the repo, including everything added since v1 (checked git log 2026-07-19):
HeroSection, HowItWorksSection, ChatInterface + SpiritualWelcomeBanner (personalized daily line), SereneMindModal, WisdomCardGenerator, StudyNotebookPage, **KGConceptMap** (new interactive Obsidian-style knowledge graph), SpiritGuidesPage, LanguageSelector, **incognito mode** (session-isolated, visually indicated in the header), **SafetyPillarsSection** (real on-site copy), **SampleWisdomSection** (real quotes from Sri Preethaji & Sri Krishnaji, with YouTube source links). No invented features, no invented claims.

**Blocker, unresolved: I cannot create the account.** Creating accounts / entering passwords, and receiving an already-authenticated session, are hard rules on my end that don't bend even when asked directly — a live logged-in session handed to me is functionally the same as a credential handoff. You have two options: record the login + chat steps yourself (I can still handle the editing/captions afterward from the footage), or set up a separate, revocable demo account you control and record with that. Also worth checking either way: does a no-signup guest path exist? That would remove a whole step and make the open faster regardless of which option you pick.

---

## 0:00–0:08 — THE PROBLEM (cold open)

**Visual:** Black screen, one typed line fades in over a plain dark background: "why do I feel empty at 2am" — no app UI yet.

**Caption:** *Spiritual guidance shouldn't require an appointment.*

---

## 0:08–0:18 — THE TURN

**Visual:** Hard cut to the real hero — "Discover Your Beautiful State," lotus/water background, "Guided by Ancient Wisdom, Powered by AI" badge.

**Caption:** *AskMukthiGuru — an AI guide grounded in the teachings of Sri Preethaji & Sri Krishnaji.*

**Click cue:** Quick scroll past How It Works (Start a Conversation → Share Your Heart → Receive Wisdom → Experience Serenity), ~2s, don't linger.

---

## 0:18–0:38 — THE CONVERSATION (core, longest beat)

**Visual:** Click "Start Chat." Personalized welcome banner appears (daily spiritual line). Type one real, human question. Response streams in.

**Caption:** *Grounded in real teachings. Not a generic chatbot.*

**Click cue:** If a language switch is fast and clean, show it once as a multilingual proof point — cut it if it adds friction.

**Note — read before recording:** pick a question likely to hit a fast path. The live instance has measured p95 latency up to 60 seconds; we are not sitting on a spinner for a minute on camera. If the first question hangs, cut and retry with something simpler or previously asked.

---

## 0:38–0:48 — WHEN IT GETS HEAVY (Serene Mind)

**Visual:** A distress-toned message triggers the Serene Mind modal — show one guided breath step, then cut away. Don't run the full meditation on camera.

**Caption:** *If a moment feels heavier, it doesn't just talk — it guides you through a real practice.*

---

## 0:48–1:03 — CARRY IT WITH YOU (fast montage, ~4s per cut)

1. **Wisdom Card Generator** — turn a teaching into a shareable card.
2. **Study Notebook** — save/bookmark a teaching for later.
3. **Sample Wisdom carousel** (landing page) — one real quote card on screen, e.g. *"A beautiful state is a state of connection, joy, love, compassion, vitality, and passion."* — Sri Preethaji.
4. **Knowledge Graph** — the new interactive concept map, one smooth pan across a couple of connected nodes. Genuinely new, visually the most striking thing in the app right now — worth the beat.

**Caption:** *Save it. Share it. See how it all connects.*

---

## 1:03–1:13 — TRUST (the site's own real language, not an invented claim)

**Visual:** Safety Pillars section — Privacy First / Compassionate Boundaries panels.

**Caption:** *Gated conversation history. Zero model training. Your journey stays yours.*

*(This is the actual live on-site copy, not a rewrite. Deliberately avoiding "zero external calls" — the backend's LLM provider is OpenRouter, an external API — so the claim stays to what's actually true and already published: no training on your data, gated history.)*

---

## 1:13–1:22 — CLOSE

**Visual:** Return to hero, logo centered, CTA visible.

**Caption:** *AskMukthiGuru. Ancient wisdom. Available now. Free to start.*

---

## Shot list summary (for whoever records)
1. Cold open text card (built in editing, doesn't need the app on screen)
2. Hero → quick scroll past How It Works
3. Start Chat → welcome banner → one real, fast question → streamed answer
4. Trigger Serene Mind → one breath step
5. Wisdom Card generation
6. Study Notebook save
7. Sample Wisdom quote carousel (landing page)
8. Knowledge Graph pan
9. Safety Pillars section
10. Back to hero, close

## Open items before this is final
- **Does chat require signup, or does it work as a guest?** Determines whether step 3 needs a login first, and whether the account-creation blocker above even applies.
- You said "1–1.5 minutes end-to-end" — this cut is ~80s, hits every beat once. Dropping the Knowledge Graph beat gets it under 70s if you want it tighter.
- "Interactive and animated": I can deliver animated captions/titles and clean transitions (fades, timed text, subtle motion) in editing via ffmpeg. I can't hand-produce custom motion-graphic characters or a fully choreographed animation sequence — flagging so expectations are calibrated before the edit, not after.
