

# Fix Plan: Landing Page, Chat History, Voice Input & Security

## Issues to Fix

### 1. Remove 3D Lotus Component & Restore Gold Balls
The `LotusFlower3D` component on the landing page doesn't look good. It will be removed from `HeroSection.tsx`. The `FloatingParticles` component (gold balls rising from bottom to top) is already present and will remain as the primary visual effect.

**Files to modify:**
- `src/components/landing/HeroSection.tsx` -- Remove both `LotusFlower3D` imports and instances (lines 6, 26-43)

### 2. Fix Desktop Chat History Button (Critical)
The `ChatHeader` currently shows a back-to-home arrow on desktop (`hidden sm:flex`) and a hamburger menu only on mobile (`sm:hidden`). The `DesktopSidebar` exists but is only visible on `lg:` screens, and there's no way to toggle it on medium-sized desktops. The header needs a menu button visible on desktop to toggle the sidebar.

**Files to modify:**
- `src/components/chat/ChatHeader.tsx` -- Add a sidebar toggle button that shows on `sm:` and above screens alongside the back button. Accept a new `onToggleSidebar` prop.
- `src/components/chat/ChatInterface.tsx` -- Pass the `onToggleSidebar` handler to `ChatHeader`. Show `DesktopSidebar` on `sm:` screens instead of only `lg:`.
- `src/components/chat/DesktopSidebar.tsx` -- Change `hidden lg:flex` to `hidden sm:flex` so the sidebar appears on tablet and desktop.

### 3. Fix Voice Recognition (Microphone Not Writing to Input)
The `useSpeechRecognition` hook has a critical bug: `onTranscript` and `onError` callbacks are in the `useEffect` dependency array (line 187). Since these are inline functions passed from `ChatInterface`, the recognition instance is destroyed and recreated on every render, killing any active listening session.

**Fix:** Use `useRef` to store the callbacks so the recognition instance is created once and callback refs are always up to date.

**Files to modify:**
- `src/hooks/useSpeechRecognition.ts` -- Store `onTranscript` and `onError` in refs. Remove them from the `useEffect` dependency array. This ensures the `SpeechRecognition` instance persists across renders.

### 4. Enhance FloatingParticles (Gold Balls)
The existing `FloatingParticles` component works but can be slightly improved with more visible particles and warmer glow.

**Files to modify:**
- `src/components/landing/FloatingParticles.tsx` -- Increase particle count slightly and enhance glow effect.

### 5. Security Fixes
- Ensure no `console.log` of sensitive data exists
- Validate that `dangerouslySetInnerHTML` is not used with user content
- Review AI service input sanitization

### 6. Test Cases
Update/create tests for the fixed components to prevent regressions.

**Files to modify/create:**
- `src/test/useSpeechRecognition.test.ts` -- Fix mock to match new ref-based pattern
- `src/test/LotusFlower3D.test.tsx` -- Remove (component is being deleted)

---

## Technical Details

### Voice Recognition Fix (Root Cause)

Current broken code (line 187):
```text
}, [continuous, onTranscript, onError]);
```

Every render creates new `onTranscript`/`onError` inline functions, causing the effect to re-run, which calls `recognition.abort()` in cleanup and creates a new instance -- killing any active session.

Fix: Use `useRef` for callbacks:
```text
const onTranscriptRef = useRef(onTranscript);
const onErrorRef = useRef(onError);

useEffect(() => {
  onTranscriptRef.current = onTranscript;
}, [onTranscript]);

useEffect(() => {
  onErrorRef.current = onError;
}, [onError]);

// In the main useEffect, use onTranscriptRef.current and onErrorRef.current
// Dependency array becomes: [continuous]
```

### Desktop Chat Header Fix

Current: Back button shows on `sm:`, hamburger only on mobile (`sm:hidden`)
Fix: Add a `Menu` button visible on `sm:` screens that toggles the sidebar, keeping the back button as well.

```text
ChatHeader props additions:
  onToggleSidebar?: () => void;

New button (visible sm: and above):
  <button onClick={onToggleSidebar} className="hidden sm:flex ...">
    <Menu />
  </button>
```

### DesktopSidebar Visibility Change

Change from `hidden lg:flex` to `hidden sm:flex` so the sidebar is available on all non-mobile screens.

---

## Files Summary

| File | Action | Change |
|------|--------|--------|
| `src/components/landing/HeroSection.tsx` | Modify | Remove LotusFlower3D imports and usage |
| `src/components/landing/FloatingParticles.tsx` | Modify | Enhance particle visibility |
| `src/hooks/useSpeechRecognition.ts` | Modify | Fix callback ref bug |
| `src/components/chat/ChatHeader.tsx` | Modify | Add sidebar toggle button for desktop |
| `src/components/chat/ChatInterface.tsx` | Modify | Pass sidebar toggle to header |
| `src/components/chat/DesktopSidebar.tsx` | Modify | Show on sm: screens |
| `src/test/useSpeechRecognition.test.ts` | Modify | Update tests |
| `src/test/LotusFlower3D.test.tsx` | Delete | Component removed |
| `src/components/landing/LotusFlower3D.tsx` | Delete | Component removed |

