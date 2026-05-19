import { useEffect, useRef } from 'react';

interface SwipeOptions {
  /** Fires when the user swipes from left → right past `threshold` px. */
  onSwipeRight?: () => void;
  /** Fires when the user swipes from right → left past `threshold` px. */
  onSwipeLeft?: () => void;
  /** Minimum horizontal distance (px) to register as a swipe. Default 60. */
  threshold?: number;
  /** Only trigger swipes that start within this many px of the left edge. */
  edgeOnly?: boolean;
  /** Maximum vertical drift (px) for the gesture to count as horizontal. Default 60. */
  maxVerticalDrift?: number;
  enabled?: boolean;
}

/**
 * Detects mobile swipe gestures on the window.
 * Useful for opening the conversation sheet via left-edge swipe (D20).
 */
export const useSwipeGesture = ({
  onSwipeRight,
  onSwipeLeft,
  threshold = 60,
  edgeOnly = false,
  maxVerticalDrift = 60,
  enabled = true,
}: SwipeOptions) => {
  const startRef = useRef<{ x: number; y: number; valid: boolean } | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const onStart = (e: TouchEvent) => {
      const t = e.touches[0];
      if (!t) return;
      const fromEdge = edgeOnly ? t.clientX <= 24 : true;
      startRef.current = { x: t.clientX, y: t.clientY, valid: fromEdge };
    };

    const onEnd = (e: TouchEvent) => {
      const s = startRef.current;
      startRef.current = null;
      if (!s || !s.valid) return;
      const t = e.changedTouches[0];
      if (!t) return;
      const dx = t.clientX - s.x;
      const dy = Math.abs(t.clientY - s.y);
      if (dy > maxVerticalDrift) return;
      if (dx >= threshold && onSwipeRight) onSwipeRight();
      else if (dx <= -threshold && onSwipeLeft) onSwipeLeft();
    };

    window.addEventListener('touchstart', onStart, { passive: true });
    window.addEventListener('touchend', onEnd, { passive: true });
    return () => {
      window.removeEventListener('touchstart', onStart);
      window.removeEventListener('touchend', onEnd);
    };
  }, [enabled, edgeOnly, maxVerticalDrift, onSwipeLeft, onSwipeRight, threshold]);
};
