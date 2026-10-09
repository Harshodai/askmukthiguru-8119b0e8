# Mukthi Guru — 1-Minute Product Demo Script

No prior demo script existed in the repo (searched, found nothing). This is built fresh, and every beat is tied to a real component — nothing invented.

**Before you record:** hit the live URL 2 minutes early and send one throwaway message. `ChatPage.tsx` shows a "The Guru is waking up" cold-start banner on the first Railway request — you don't want that in frame.

---

### 0:00–0:07 — Landing (`Index.tsx`, `HeroSection`)
Open the landing page. Voiceover: "Mukthi Guru — an AI spiritual guide grounded in Sri Preethaji and Sri Krishnaji's teachings. Free to use, and every answer is grounded in retrieval — not the model guessing."
Point the cursor at the Crisis Support link for one second — don't open it, just show it exists. It's a real dialog with India/US helplines, not marketing dressing.

**Before you say "private" or "doesn't make things up" on camera:** check `src/lib/aiService.ts`'s active provider mode and the backend's `LLM_PROVIDER` in whatever deployment you're recording against. On the live Railway prod deployment as configured, `LLM_PROVIDER=openrouter` — an external cloud API, not a local-only setup — so an unscoped "private" claim doesn't hold there; scope it ("your data isn't used to train other products") or only claim it when recording against a genuinely local-only (`ollama`) backend. Same for "doesn't make things up": the anti-hallucination pipeline targets <1% hallucination with graceful fallback when retrieval comes up empty (see the risk note below) — it's not a zero-hallucination guarantee. The retrieval-grounding claim itself is real and checkable via the citation panel (0:15–0:32) — lead with that, it's the actual differentiator.

### 0:07–0:15 — Grounding ritual (`PrePracticeGate.tsx` → `SereneMindModal.tsx`)
Click into chat for the first time. The pre-practice gate asks: Soul Sync, Serene Mind, or Both. Pick Serene Mind — show 3 seconds of the breathing modal, the circular breath-progress ring animating, Sri Preethaji's narrated audio audible under the voiceover. Cut before it finishes.

### 0:15–0:32 — The actual product: grounded answers (`ChatInterface.tsx`, `CitationPanel.tsx`)
Type a real question — e.g. "Why do I keep suffering in the same way?" — and let it stream a real answer from the live RAG backend (this is the default `'custom'` provider, not a canned response).
The moment the answer lands, click to open the **citation panel**. Voiceover: "Every answer comes with the source — the actual video, the actual quote. This isn't a generic chatbot paraphrasing spirituality. It's retrieval-grounded, and you can check its work."
This is the single most important beat in the whole demo — it's the product's actual differentiator, not a UI flourish.

### 0:32–0:42 — Speaks your language (`LanguageSelector.tsx`)
Click the language pill, switch to Telugu or Hindi mid-conversation. Ask a quick follow-up in that language, get a real answer back. Voiceover: "Hindi, Telugu, Tamil, and more — full voice input and text-to-speech too." (Don't say "22 languages" — only 11 are live in the UI: English, Hindi, Bengali, Telugu, Marathi, Tamil, Gujarati, Kannada, Malayalam, Assamese, Sanskrit.)

### 0:42–0:52 — Make it shareable (`WisdomCardGenerator.tsx`)
Take the best line from the answer, hit "Wisdom Card," pick a theme (Golden Hour). Show the generated image for 2 seconds. Voiceover: "Turn any teaching into something you can actually carry with you."

### 0:52–1:00 — Close on privacy (`MemoryManager.tsx`)
Cut to the Memory tab — show the force-directed knowledge graph of what the AI remembers about the user (color-coded: Beautiful State, Suffering, etc.). Voiceover: "It remembers your context to personalize — visibly, and you can delete any of it. Everything runs on open-source infrastructure, zero paid APIs at inference."

---

## What I deliberately left out
- The 6-step guided meditation flow and admin dashboard (anti-hallucination pipeline, telemetry) — real, and worth a *second*, longer demo, but they don't fit in 60 seconds without cutting the citation-panel beat, which is the actual proof point. Don't let anyone talk you into trading that for eye candy.
- Multi-persona `AssistantSwitcher` (general / relationship / locked "sky" persona) — good for a longer cut, cut here for time.

## One risk to flag
This whole script assumes the Railway backend is warm and actually returns a grounded answer with real citations on the take you record. If retrieval comes back empty or the backend is cold, you'll either get the "couldn't find relevant teachings" honest-fallback message or the wake-up banner — neither is a good demo moment. Do a dry run of the exact question you plan to ask, on camera conditions, before the real take.
