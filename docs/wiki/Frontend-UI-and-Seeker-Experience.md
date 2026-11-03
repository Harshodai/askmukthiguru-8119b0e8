# Frontend Architecture & Seeker Experience

AskMukthiGuru delivers a spiritually grounded, responsive, and contemplative digital sanctuary. Engineered with **React 18, Vite, TypeScript, and Tailwind CSS**, the frontend bridges sacred wisdom with modern web engineering. Every interaction—from meditative breathing sessions to multi-lingual spiritual inquiries—is designed to minimize cognitive load, cultivate inner stillness, and provide seamless access to the authentic teachings of **Sri Preethaji and Sri Krishnaji**.

---

## 1. High-Level Frontend Architecture

The frontend application is structured as a component-driven Single Page Application (SPA) optimized for fast time-to-interactive, zero-jank animations, and accessible keyboard navigation.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            SEEKER BROWSER CLIENT                                 │
│      React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Framer Motion      │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│        SEEKER SURFACES          │             │         ADMIN SURFACES          │
│ • Chat Sanctuary & Composer     │             │ • Ingestion Job Dashboard       │
│ • Ekam Golden Orb & Serene Mind │             │ • OKF Doctrine Curation Queue   │
│ • Practice Timer & Audio Strip  │             │ • Telemetry & Latency Profiler  │
│ • Sadhana Rhythm Mandala        │             │ • Speaker Attribution Review    │
│ • Second Brain Vault & Notes    │             │ • RAG Flow Graph Visualizer     │
└────────────────┬────────────────┘             └────────────────┬────────────────┘
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             CLIENT INFRASTRUCTURE                                │
│ ┌──────────────────────┐ ┌──────────────────────┐ ┌────────────────────────────┐ │
│ │  TanStack Query v5   │ │   i18next Engine     │ │   Web Audio / Speech API   │ │
│ │ (Cache & Deduping)   │ │ (14 Indic Languages) │ │  (Haptic Audio & Voice STT)│ │
│ └──────────────────────┘ └──────────────────────┘ └────────────────────────────┘ │
│ ┌──────────────────────┐ ┌──────────────────────┐ ┌────────────────────────────┐ │
│ │   SSE Event Stream   │ │ Supabase Client SDK  │ │ YouTube Embed Guard        │ │
│ │  (Token-by-Token)    │ │ (Auth & User Vault)  │ │ (Error 153 PostMessage)    │ │
│ └──────────────────────┘ └──────────────────────┘ └────────────────────────────┘ │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ HTTPS / WSS / SSE
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     FASTAPI GATEWAY (Port 8000 / Nginx 80)                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Core Frontend Tech Stack

| Technology | Version / Library | Architectural Role |
|---|---|---|
| **Framework** | React 18.3+ | Virtual DOM, Suspense boundaries, concurrent rendering |
| **Build Tool** | Vite 5.x | Ultra-fast HMR, ES module bundling, tree-shaking |
| **Language** | TypeScript 5.5+ | Strict type safety, shared API schemas, contract verification |
| **Styling** | Tailwind CSS 3.4+ | Utility-first styling, spiritual palette (`ojas`, `prana`, `soma`) |
| **UI Primitives** | Radix UI | Headless accessible components (Dialog, Tabs, Tooltip, Dropdown) |
| **Animations** | Framer Motion 11+ | Calibrated contemplative transitions, sacred geometry layout shifts |
| **Icons** | Lucide React | Clean, lightweight stroke icons |
| **Data Fetching** | TanStack Query v5 | Server-state caching, automatic retry backoff, cache invalidation |
| **Localization** | i18next & react-i18next | Multi-lingual routing, RTL support, 14 Indic language catalogs |

---

## 2. Ekam Golden Orb & Sacred Geometry

The visual identity of AskMukthiGuru is anchored by the **Ekam Golden Orb** (`src/components/common/EkamGoldenOrb.tsx`), representing the sacred *Svarna Golakam* (Hiranyagarbha) of Ekam—the universal field of oneness, divine consciousness, and the Beautiful State.

```
                       ┌─────────────────────────┐
                       │   Outer Radiance Aura   │
                       │ (r=10, dasharray 1.5 2) │
                       └────────────┬────────────┘
                                    │
                       ┌────────────┴────────────┐
                       │ Middle Ring of Oneness  │
                       │  (r=7.5, stroke 1.25)   │
                       └────────────┬────────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
     ┌───────────────────────┐             ┌───────────────────────┐
     │  4 Cardinal Rays      │             │   4 Ordinal Rays      │
     │ (Top, Bottom, L, R)   │             │ (45° Diagonal Angles) │
     └───────────┬───────────┘             └───────────┬───────────┘
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    ▼
                       ┌─────────────────────────┐
                       │ Inner Golden Orb Sphere │
                       │    (r=4.5, fill ojas)   │
                       └────────────┬────────────┘
                                    │
                       ┌────────────┴────────────┐
                       │  Central Bindu (Core)   │
                       │ (r=1.5, #FFFDF0 95% op) │
                       └─────────────────────────┘
```

### 2.1 Geometric Decomposition
The component is rendered as an SVG vector with sub-pixel mathematical precision:
1. **Outer Subtle Radiance Aura**: A dashed concentric circle ($r=10$) with `strokeDasharray="1.5 2"` and `opacity="0.55"`, simulating the shimmering aura of enlightened presence.
2. **Middle Ring of Oneness**: A continuous orbital stroke ($r=7.5$, width $1.25$, opacity $0.8$) signifying the unbroken wholeness of life.
3. **8 Rays of Divine Grace**:
   - 4 Cardinal Rays: Vertical and horizontal axes connecting the seeker with transcendent dimensions.
   - 4 Ordinal Rays: 45° diagonal vectors radiating outward at balanced lengths.
4. **Inner Golden Sphere**: A solid disc ($r=4.5$) reflecting the dense golden light of Ekam.
5. **Central Bindu (Core Consciousness)**: A luminous white-gold focal point ($r=1.5$, `#FFFDF0`, opacity $0.95$) representing the unconditioned observer witnessing all existence.

---

## 3. Serene Mind Modal: 3-Stage Guided Contemplation

The **Serene Mind Modal** (`src/components/chat/SereneMindModal.tsx`) provides an on-demand sanctuary when seekers experience acute distress, anxiety, or emotional turbulence. Built on clinical-grade safety gating, it guides the seeker through a structured 3-stage practice:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SERENE MIND CONTEMPLATION PIPELINE                       │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│   STAGE 1: INQUIRE   │   STAGE 2: BREATHE   │     STAGE 3: CONTEMPLATE      │
│  "Soul Inquire"      │   "Sacred Space"     │     "Rest in Awareness"       │
├──────────────────────┼──────────────────────┼───────────────────────────────┤
│ • Acknowledge state  │ • 4-4-4-4 Box Rhythm │ • Dissolve self-centric loop  │
│ • Suffering vs       │ • Sri Preethaji      │ • Witness thoughts without    │
│   Beautiful state    │   Guided Audio/Video │   judgment or struggle        │
│ • Identify loop      │ • Real-time circular │ • Cultivate stillness and     │
│   (fear, hurt, pride)│   progress timer     │   interconnectedness          │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

### 3.1 Practice Mechanics & Audio/Video Dual Mode
* **Dual Guidance Surface**:
  - **Audio Meditation Mode**: Driven by high-fidelity audio streams with haptic breathing cues.
  - **Video Guidance Mode**: Plays Sri Preethaji’s authentic Serene Mind teaching discourse (`igSp4H0OWLE`) via the privacy-hardened YouTube embed player.
* **Non-Trapping Safety Contract**:
  - Even when triggered by high-distress classification, the modal **never traps** the seeker.
  - Close (`X`), Escape key, and "Skip to Wisdom" controls remain visible and active at all times, preserving user autonomy (`isGated=false`).
* **Accessible Focus Management**: Utilizes the custom `useDialogFocus` hook to trap focus within the active dialog for screen readers and keyboard navigation, automatically restoring focus upon closure.
* **Persistent Session Telemetry**: Upon completion, the session is recorded via `completeMeditationSession(id, duration, cycleCount)` in `src/lib/meditationStorage.ts`, updating the seeker’s sadhana history.

---

## 4. ThinkingPills: Real-Time Sacred Pipeline Transparency

During streaming inference, AskMukthiGuru avoids generic loading spinners. Instead, **ThinkingPills** (`src/components/chat/ThinkingPills.tsx`) communicates pipeline execution in real-time, mapping complex backend operations to spiritually resonant language:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           THINKING PILLS DISPLAY                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ ◉ Searching sacred wisdom... [Step 4 of 12]                 00:04 ▼   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  Expanded Details:                                                          │
│  ├─ ✓ Safety check                                                          │
│  ├─ ✓ Understanding query                                                   │
│  ├─ ◉ Searching sacred wisdom (Dual Qdrant + Neo4j Graph traversal)         │
│  ├─ ○ Refining relevance (Cross-Encoder reranking)                          │
│  ├─ ○ Synthesizing wisdom (Context engineering & boundary assembly)         │
│  └─ ○ Verifying sacred teachings (Sentence-level grounding verification)    │
│                                                                             │
│  Sacred Reflection during generation:                                       │
│  "Suffering grows from obsessive self-engagement. When attention softens    │
│   away from 'me and my story', calm arises on its own."                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Node to Seeker-Facing Label Mapping

| Backend LangGraph Node | Seeker-Facing Pill Label | Spiritual Purpose |
|---|---|---|
| `guardrails` / `distress_check` | **Safety check** | Protects seeker vulnerability; screens for crisis keywords |
| `intent_router` / `decompose_query` | **Understanding query** | Discerns spiritual intent; breaks complex inquiries down |
| `retrieve` / `hyde` / `traversal` | **Searching sacred wisdom** | Queries Qdrant dense vectors & Neo4j OKF knowledge graph |
| `rerank_documents` | **Refining relevance** | Cross-encoder MiniLM ranking to surface highest fidelity spans |
| `grade_documents` / `crag` | **Filtering relevance** | Discards irrelevant context; triggers CRAG query reformulations |
| `enrich_context` / `synthesize` | **Synthesizing wisdom** | Enforces teacher persona boundaries and context assemblies |
| `generate_answer` / `reflect` | **Composing guidance** | Drafts teachings strictly referencing retrieved citations |
| `verify_citations` / `grounding` | **Verifying sacred teachings** | Self-RAG sentence-level verification against authentic transcripts |

### 4.2 Dynamic Sacred Wisdom Pool (`useWisdomTips`)
While the backend executes its 12-layer verification graph, the client displays rotating wisdom tips (`useWisdomTips.ts`):
* Fetched asynchronously from `GET /api/teachings/tips`.
* Cached in `localStorage` for 7 days (`CACHE_TTL_MS = 604,800,000`).
* Rotates automatically every 8 seconds with smooth cross-fade typography.
* Degrades silently to `STATIC_FALLBACK_TIPS` (paraphrased core teachings marked with empty `teacher: ''` to guarantee no false quote attribution occurs if network connectivity drops).

---

## 5. ChatComposer & Multi-Lingual Architecture

The **ChatComposer** (`src/components/chat/ChatComposer.tsx`) serves as the seeker's input sanctuary. It supports text, voice dictation, slash commands, and multi-file evidence attachment.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                CHAT COMPOSER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Ask a spiritual question or type / for practices...                     │ │
│ │                                                                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ ┌──────────────────────┐  ┌───────────────────────────────────────────────┐ │
│ │ 📎 Attachment Slider │  │ [PDF: Karma Discourses]  [IMG: Journal Note]   │ │
│ └──────────────────────┘  └───────────────────────────────────────────────┘ │
│                                                                             │
│ ┌──────────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────────────┐ │
│ │ 🌐 English (IN)  │ │ 🎙️ Voice STT  │ │ 🔊 Sacred TTS │ │ ⬆ Send (Enter) │ │
│ └──────────────────┘ └───────────────┘ └───────────────┘ └────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 The 14 Supported Indic Languages
AskMukthiGuru natively supports 14 Indic languages alongside English, matching Sarvam AI's multilingual speech and token models:

| Code | Language | Native Script | BCP-47 Tag |
|---|---|---|---|
| `en` | English (India) | English | `en-IN` |
| `hi` | Hindi | हिन्दी | `hi-IN` |
| `te` | Telugu | తెలుగు | `te-IN` |
| `ta` | Tamil | தமிழ் | `ta-IN` |
| `kn` | Kannada | ಕನ್ನಡ | `kn-IN` |
| `ml` | Malayalam | മലയാളം | `ml-IN` |
| `mr` | Marathi | मराठी | `mr-IN` |
| `bn` | Bengali | বাংলা | `bn-IN` |
| `gu` | Gujarati | ગુજરાતી | `gu-IN` |
| `pa` | Punjabi | ਪੰਜਾਬੀ | `pa-IN` |
| `or` | Odia | ଓଡ଼ିଆ | `or-IN` |
| `sa` | Sanskrit | संस्कृतम् | `sa-IN` |
| `ur` | Urdu | اُردُو | `ur-IN` |
| `as` | Assamese | অসমীয়া | `as-IN` |

### 5.2 Input Capabilities & Keyboard Shortcuts
* **Keyboard Navigation**:
  - `Enter`: Submit question (with immediate optimistic UI rendering).
  - `Shift + Enter`: Insert soft line break.
  - `/`: Open Slash Command Palette (`SlashCommandMenu.tsx`) for instant access to Serene Mind, Soul Sync, Breath Meditation, and Practice Logs.
  - `Escape`: Dismiss open menus, tooltips, or modals.
* **Persistent Attachment Slider**: Horizontal scroll carousel accommodating up to 5 multi-modal attachments (max 10MB each) with instant OCR text extraction for handwritten journal reflections.
* **Haptic Audio Integration**: Subtle, soothing synthesized acoustic clicks (`hapticAudio.ts`) providing sensory feedback on message dispatch, meditation bell intervals, and tab changes.

---

## 6. Personalise Tab, Sadhana Mandala & Reflection Dock

Seeker profile and spiritual progression are managed within `/profile` across 4 dedicated workspaces: **Journey, Personalise, Memory, and Settings**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PROFILE WORKSPACE TABS                             │
│       [ 🧭 Journey ]    [ 🎛️ Personalise ]    [ 📖 Memory ]    [ ⚙️ Settings ] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Sadhana Rhythm Mandala & Meditation Heatmap
The **Sadhana Heatmap** (`src/components/profile/SadhanaHeatmap.tsx`) renders an activity matrix inspired by GitHub's contribution graph, tracking daily meditation and contemplative practice:

```
  Mon  ░░  ▒▒  ██  ██  ░░  ▒▒  ██  ██  ░░  ▒▒
  Wed  ░░  ░░  ▒▒  ██  ██  ▒▒  ██  ░░  ▒▒  ██
  Fri  ░░  ▒▒  ██  ██  ██  ██  ██  ▒▒  ██  ██
  Sun  ░░  ░░  ▒▒  ▒▒  ██  ██  ██  ██  ██  ██

  Legend:  ░░ Rest (<1m)   ▒▒ Short (<10m)   ▓▓ Steady (10-20m)   ██ Deep (>20m)
```

#### Strict Objectivity Invariant:
* Intensity classification is calculated **exclusively from measured duration**:
  - `rest`: $0\text{ minutes}$
  - `short`: $< 10\text{ minutes}$
  - `steady`: $10 - 20\text{ minutes}$
  - `deep`: $\ge 20\text{ minutes}$
* **Ethical Boundary**: The UI never infers spiritual enlightenment, holiness, or inner state quality from practice time. Classification is reported honestly as duration alone.

### 6.2 Guru Tone & Personalization Preferences
Within the **Personalise** tab (`/profile?tab=profile`), seekers customize their guidance experience:
* **Guru Tone (`GuruTone`)**:
  - `gentle`: Soft, nurturing, and compassionate discourse style.
  - `direct`: Clear, concise, laser-focused spiritual instructions.
  - `traditional`: Rich in Sanskrit terminology and classical Vedic discourse structures.
  - `philosophical`: Analytical, addressing existential mechanics and universal laws.
* **Daily Reflections Dock & Study Notebook**:
  - `StudyNotebookPage.tsx` allows seekers to bookmark specific teacher discourse passages, add personal commentary, and export reflections as markdown or PDF.

---

## 7. YouTube Embed Player & Error 153 Mitigation

Embedding YouTube discourse clips within an AI conversation interface introduces significant browser-level failure modes: YouTube iframe players frequently fail due to owner embedding restrictions (Error 101/150), regional constraints, ad-blocker interference, or strict Content Security Policies (CSP). Crucially, **standard `<iframe>` elements do not trigger DOM `error` events**, causing broken players to hang indefinitely as dead black boxes.

AskMukthiGuru implements a battle-tested, 4-layer defense in `DiscourseAudioStrip.tsx`, `CitationCard.tsx`, and `useYouTubeEmbedError.ts`:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    YOUTUBE EMBED HARDENING PIPELINE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Privacy-Enhanced URL:                                                    │
│    https://www.youtube-nocookie.com/embed/{videoId}                         │
│                                                                             │
│ 2. Strict Origin Handshake:                                                 │
│    &origin=${encodeURIComponent(window.location.origin)}&enablejsapi=1      │
│                                                                             │
│ 3. Referrer Policy Isolation:                                               │
│    referrerPolicy="strict-origin-when-cross-origin"                         │
│                                                                             │
│ 4. Two-Way PostMessage Liveness & Timeout Guard (useYouTubeEmbedError):      │
│    ┌────────────────────────┐                   ┌────────────────────────┐  │
│    │ Host Window Listener   │                   │ YouTube IFrame Player  │  │
│    │ (useYouTubeEmbedError) │                   │ (youtube-nocookie.com) │  │
│    └───────────┬────────────┘                   └───────────┬────────────┘  │
│                │                                            │               │
│                │ ──── 1. onFrameLoad: send "listening" ───► │               │
│                │                                            │               │
│                │ ◄─── 2. onReady / onStateChange ────────── │ (Alive!)      │
│                │      (Clears 10s timeout timer)            │               │
│                │                                            │               │
│                │ ◄─── 3. onError [2, 5, 100, 101, 150] ──── │ (Blocked)    │
│                ▼                                            ▼               │
│    ┌─────────────────────────────────────────────────────────────────────┐  │
│    │ Fallback UI Triggered:                                              │  │
│    │ "Playback unavailable in embed. Watch directly on YouTube ↗"        │  │
│    └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.1 Multi-Layer Mitigation Details
1. **Privacy-Enhanced Host (`youtube-nocookie.com`)**: Mitigates 3rd-party cookie deprecation warnings and prevents unwanted tracking cookies from blocking playback in privacy-focused browsers (Brave, Safari ITP).
2. **Explicit Origin Parameter**: Passing `origin=${encodeURIComponent(window.location.origin)}` satisfies YouTube’s widget API cross-origin handshake requirements, eliminating Error 153 (`origin_not_permitted`).
3. **Strict Referrer Policy**: Setting `referrerPolicy="strict-origin-when-cross-origin"` guarantees that YouTube receives valid origin data while stripping sensitive query parameters.
4. **PostMessage Liveness Timer (`useYouTubeEmbedError.ts`)**:
   - Sends the IFrame API `listening` message as soon as the iframe fires its `load` event.
   - Arms an `EMBED_LOAD_TIMEOUT_MS = 10,000` countdown timer.
   - If an unplayable error code (`2, 5, 100, 101, 150`) is received via postMessage, or if no proof of life arrives before the 10-second timer expires, `embedError` is set to `true`.
   - The UI immediately swaps the black box for a graceful fallback card featuring the video thumbnail and a verified link to open the discourse on YouTube at the exact start offset.

---

## 8. Related Wiki Documentation

* [System Architecture Overview](Architecture-Overview) — Multi-tier topology, edge proxying, and service ports.
* [12-Layer RAG Pipeline](Architecture-RAG-Pipeline) — Streaming SSE event generation and verification engine.
* [Second Brain Vault & Memory](Memory-Second-Brain-Vault) — User memory cards, notes dock, and bi-temporal sync.
* [REST & Streaming API Reference](API-Reference) — Full specification of `/api/chat`, `/api/chat/stream`, and SSE schemas.
