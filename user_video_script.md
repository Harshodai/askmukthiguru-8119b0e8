# AskMukthiGuru — USER Demo Video Script
Target length: 100–110 seconds | 1920x1080 | Captions ON | Synthetic voiceover

Ground truth used: HeroSection ("Discover Your Beautiful State"), HowItWorksSection (Start a Conversation → Share Your Heart → Receive Wisdom → Experience Serenity), ChatInterface, SereneMindModal, WisdomCardGenerator, DailyTeaching, PracticesPage, StudyNotebookPage, KnowledgeGraphPage, SpiritGuidesPage, LanguageSelector, MemoryManager. No invented features.

---

## 0:00–0:10 — THE PROBLEM (cold open, no app on screen yet)

**Visual:** Black screen, slow fade into a phone/laptop showing a generic search bar being typed into: "why do I feel empty" — then cut away. No branding yet.

**VO:** "When something's heavy on your heart at 2am, a search engine gives you noise. A hotline gives you a queue. Where do you actually go?"

**Caption:** *Spiritual guidance shouldn't require an appointment.*

---

## 0:10–0:22 — THE TURN (reveal)

**Visual:** Cut to the AskMukthiGuru landing page hero — "Discover Your Beautiful State" headline, hero image, floating particles.

**VO:** "This is AskMukthiGuru — an AI guide grounded in the teachings of Sri Preethaji and Sri Krishnaji, available the moment you need it."

**Click cue:** Landing page loaded, scroll slowly down to "How It Works" section.

---

## 0:22–0:38 — HOW IT WORKS (4-step section, already built into the app)

**Visual:** HowItWorksSection scrolls into view: Start a Conversation → Share Your Heart → Receive Wisdom → Experience Serenity.

**VO:** "Start a conversation. Share what's actually going on. Receive guidance drawn from real teachings — not generic self-help. And when you need it, be walked through a guided practice to find calm."

**Click cue:** Click "Start Your Journey" / navigate to Chat.

---

## 0:38–0:55 — THE CONVERSATION (core feature)

**Visual:** ChatInterface. Type a real, human question (e.g., "I keep overreacting to small things at work and I don't know why"). Response streams in with citations/teaching references visible.

**VO:** "Every answer is grounded in the actual teachings — not a generic chatbot guessing. It remembers your journey, so guidance builds over time instead of starting from zero every time."

**Click cue:** Show ChatMessage with citation/source reference. Briefly show LanguageSelector switching language (multilingual proof point) if it's a quick, clean click.

---

## 0:55–1:08 — WHEN IT GETS HEAVY (Serene Mind)

**Visual:** Trigger a message expressing distress → SereneMindModal opens, guided breathing/meditation flow begins.

**VO:** "If a moment feels heavier, AskMukthiGuru doesn't just talk — it gently guides you through a real meditation practice, right there, in the moment."

**Click cue:** Show one guided breath step, then move on — don't run the full meditation.

---

## 1:08–1:20 — CARRY IT WITH YOU

**Visual:** Quick montage (3 fast cuts, ~4s each):
1. WisdomCardGenerator — turning a teaching into a beautiful shareable card.
2. StudyNotebookPage — saving/bookmarking a teaching for later.
3. DailyTeaching — a short daily reflection on open.

**VO:** "Save what moves you. Turn it into a wisdom card to share. Come back each day for a new teaching."

---

## 1:20–1:32 — TRUST (the quiet differentiator)

**Visual:** Simple on-screen text over a calm background — no technical dashboard, just the promise.

**VO:** "Every answer is checked against the actual teachings before it reaches you — not internet guesses, not made-up scripture."

**Caption:** *Grounded in the real teachings. Verified before you see it.*

*(Rewritten — see note to Harsha: the original "zero external tracking / stays private" claim has been removed. It doesn't hold up against your own .env, which has `LLM_PROVIDER=openrouter` — an external cloud API — not local-only inference. Putting a false privacy claim in a public marketing video is a real liability; this version claims only what's actually true: RAG-grounded, anti-hallucination answers.)*

---

## 1:32–1:45 — CLOSE

**Visual:** Return to the hero landing page, logo centered, CTA button visible.

**VO:** "AskMukthiGuru. Ancient wisdom. Available now."

**Caption:** *Start your journey — free.*

**End card:** URL / CTA button.

---

## Shot list summary (for the recorder)
1. Generic search bar typing (can be a plain browser/text mockup, not the app)
2. Landing page hero, scroll to How It Works
3. Click into Chat, type real question, show streamed answer + citation
4. Trigger Serene Mind, show one breathing step
5. Wisdom Card generation
6. Study Notebook save
7. Daily Teaching open
8. Back to landing page for close

## Flag before recording
- Confirm the "privacy-first / zero external tracking" claim is true of the live instance we're recording — don't put an unverifiable claim in a marketing video.
- Confirm which LLM provider is live (Sarvam cloud vs local Ollama) — if it's `sarvam_cloud`, the "zero external calls" line needs softening to avoid a false claim.
