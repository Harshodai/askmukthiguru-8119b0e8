/**
 * Return keyboard focus to a control after something unmounted the element that
 * held it (NEW-A11Y-6, A11Y-08, WCAG 2.4.3). Without this, focus falls to <body>
 * and a keyboard or screen-reader user starts again from the top of the page.
 *
 * Focus is only moved when it is "free": on <body>, or on an element that is
 * gone or disabled. A seeker who put focus somewhere on purpose keeps it. The
 * target may mount late (lazy chunk, exit animation), so the move retries on
 * animation frames for a bounded time.
 */
export function focusIsFree(active: Element | null): boolean {
  return (
    !active ||
    active === document.body ||
    !active.isConnected ||
    (active as HTMLButtonElement).disabled === true
  );
}

export interface FocusWhenFreeOptions {
  maxMs?: number;
  /** Keep waiting while focus is still on something that is about to go (an
   *  exiting dialog) instead of giving up. Default false: a live element that
   *  holds focus is taken as the seeker's choice. */
  waitForFree?: boolean;
}

/** @returns a cancel function. */
export function focusWhenFree(
  getTarget: () => HTMLElement | null | undefined,
  { maxMs = 5000, waitForFree = false }: FocusWhenFreeOptions = {},
): () => void {
  const deadline = performance.now() + maxMs;
  let raf = 0;
  const tick = () => {
    if (!focusIsFree(document.activeElement)) {
      if (waitForFree && performance.now() < deadline) raf = requestAnimationFrame(tick);
      return;
    }
    const target = getTarget();
    if (target?.isConnected) {
      target.focus();
      if (document.activeElement === target) return;
    }
    if (performance.now() < deadline) raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(raf);
}
