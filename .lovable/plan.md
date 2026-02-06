

# AskMukthiGuru Enhancement Plan
## Comprehensive Upgrade for Polished Experience

---

## Overview
This plan addresses all requested improvements: page transitions, chat micro-animations, API service layer, meditation tracking, mobile optimization, guru photos, and spelling fixes.

---

## 1. Add Guru Photo to "Meet the Spiritual Guides" Section

**What we'll do:**
- Copy the uploaded photo (PK.jpg) of Sri Preethaji & Sri Krishnaji to the project
- Replace the Sun icon placeholder with their actual photo
- Add a beautiful glassmorphic frame with golden glow effect

**File changes:**
- Copy `user-uploads://PK.jpg` to `src/assets/gurus-photo.jpg`
- Update `src/components/landing/MeetTheGurusSection.tsx` to use the photo

---

## 2. Smooth Page Transitions

**What we'll do:**
- Create an `AnimatedLayout` wrapper component using Framer Motion
- Add smooth fade/slide transitions when navigating between Landing and Chat pages
- Use `AnimatePresence` with location-based key changes

**New file:**
- `src/components/layout/AnimatedLayout.tsx` - Page transition wrapper

**Modified files:**
- `src/App.tsx` - Wrap routes with AnimatedLayout

---

## 3. Enhanced Chat Interface Micro-Animations

**What we'll do:**
- Add staggered entrance animations for messages on load
- Enhanced message bubble animations with spring physics
- Input field focus glow animation
- Send button pulse on active state
- Smooth typing indicator with wave effect
- Avatar glow pulse on new messages

**Modified files:**
- `src/components/chat/ChatInterface.tsx` - Enhanced animations
- `src/components/chat/ChatMessage.tsx` - Improved message animations
- `src/index.css` - Additional keyframes for micro-animations

---

## 4. API Service Layer (src/lib/aiService.ts)

**What we'll do:**
Create a clean abstraction layer that makes it easy to swap between:
1. Static placeholder responses (current)
2. Your fine-tuned model endpoint (future)
3. Any other AI API

**New file structure:**
```text
src/lib/aiService.ts
├── AIConfig interface (endpoint, apiKey, model settings)
├── AIProvider enum (PLACEHOLDER, CUSTOM_ENDPOINT, OPENAI)
├── sendMessage() - Main function to get responses
├── setProvider() - Switch between providers
└── Placeholder response fallback
```

**Modified files:**
- `src/components/chat/ChatInterface.tsx` - Use aiService instead of direct localStorage

---

## 5. Meditation Session Tracking

**What we'll do:**
- Create a meditation storage system that tracks:
  - Session start/end timestamps
  - Duration completed
  - Breath cycles completed
  - Completion status
- Save to localStorage with key `askmukthiguru_meditation_sessions`
- Show meditation history/stats (optional UI in footer)

**New file:**
- `src/lib/meditationStorage.ts` - Session persistence logic

**Modified files:**
- `src/components/chat/SereneMindModal.tsx` - Track and save completed sessions

---

## 6. Mobile Optimization with Bottom Sheet

**What we'll do:**
Based on the reference screenshot, create a mobile-optimized layout:

**Features:**
- Bottom sheet navigation for mobile (using vaul drawer)
- Conversation sidebar that slides up from bottom on mobile
- Chat header with guru photo (small circular avatar)
- "New Conversation" button (for future multi-conversation support)
- Recent conversations list UI placeholder
- Safe area padding for notch devices
- Touch-friendly tap targets (minimum 44px)

**New files:**
- `src/components/chat/MobileConversationSheet.tsx` - Bottom sheet for conversations
- `src/components/chat/ChatHeader.tsx` - Responsive header with guru photo

**Modified files:**
- `src/components/chat/ChatInterface.tsx` - Mobile-responsive layout
- `src/index.css` - Mobile-specific styles and safe areas

---

## 7. Spelling Fixes

**Verification needed:**
I searched the codebase and found **"AskMukthiGuru"** is consistently spelled correctly throughout. The branding uses:
- `AskMukthiGuru` (with "th" - correct spelling)
- Storage key: `askmukthiguru_chat_history`

If you've seen "mukti" (without the 'h') somewhere specific, please point it out. Otherwise, the current codebase appears clean.

---

## Technical Details

### Page Transition Component
```text
AnimatedLayout uses:
- AnimatePresence with mode="wait"
- Fade + slight Y-axis slide (20px)
- Duration: 0.3s with ease-out
- Key based on location.pathname
```

### AI Service Architecture
```text
interface AIConfig {
  provider: 'placeholder' | 'custom' | 'openai';
  endpoint?: string;
  apiKey?: string;
  systemPrompt?: string;
}

// Easy swap example:
setAIProvider({
  provider: 'custom',
  endpoint: 'https://your-finetuned-model.com/api',
  apiKey: process.env.API_KEY
});
```

### Meditation Session Schema
```text
interface MeditationSession {
  id: string;
  startedAt: Date;
  completedAt: Date | null;
  durationSeconds: number;
  breathCycles: number;
  completed: boolean;
}
```

### Mobile Bottom Sheet Behavior
- Appears when tapping hamburger menu or conversation list icon
- Swipe down to dismiss
- Contains: Recent conversations, New conversation button, Serene Mind quick access
- Matches the warm orange theme from reference screenshot

----------
UX but misses a few critical functional and compliance components required for a winning submission.
Here are 4 essential additions to ensure your prototype meets the "Mental Health" and "Sovereign AI" criteria:
8) Safety & Disclaimer Layer (Crucial for AIKosh)
• Why: Mental health apps must explicitly state they do not replace professional help. The IndiaAI guidelines require "Trust" and "Transparency" regarding AI limitations12.
• Action: Add a dismissible "Guardian Modal" on first load stating this is an AI spiritual companion, not a doctor.
• Files:
    ◦ Create src/components/common/SafetyDisclaimer.tsx
    ◦ Update src/App.tsx to mount it on initialization.
9) The "Serene Mind" Visual Trigger (The Flame)
• Why: The sources explicitly describe the Serene Mind practice as visualizing a "tiny flame" at the eyebrow center34. Standard chat UI is insufficient for this; you need a visual focal point to guide the 3-minute breathwork.
• Action: Create a specific overlay or animation that activates when the "Serene Mind" mode is triggered.
• Files:
    ◦ Create src/components/meditation/FlameFocus.tsx (using CSS glow effects or a Lottie animation).
    ◦ Update SereneMindModal.tsx to include this visual.
10) Language/Voice Toggle (Bhashini Preparation)
• Why: To win the IndiaAI Challenge, "Indic Language Enablement" is a top priority56. Even if the backend isn't fully ready, the UI must show the intent to support Indian languages (e.g., Hindi, Telugu).
• Action: Add a language selector dropdown and a "Voice Mode" toggle (speaker icon) in the input area.
• Files:
    ◦ Update src/components/chat/ChatInput.tsx
    ◦ Update src/lib/aiService.ts to accept a language parameter.
11) Connection Status (Local vs. Cloud)
• Why: Since you are demoing on a 4GB VRAM laptop using a local model (Ollama/vLLM)78, the UI needs to handle "cold starts" or local inference delays gracefully.
• Action: Add a subtle status indicator (e.g., "Connecting to Guru..." or "Offline Mode") to manage user expectations during local inference.
• Files:
    ◦ Update src/components/chat/ChatHeader.tsx

