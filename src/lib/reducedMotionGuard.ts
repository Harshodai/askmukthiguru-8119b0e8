/**
 * Stop decorative looping animation under "reduce motion" (NEW-A11Y-8, A11Y-12,
 * WCAG 2.2.2 Pause, Stop, Hide). CSS loops are stopped in index.css and
 * framer-motion transform motion by <MotionConfig reducedMotion="user">, but
 * framer's looping opacity pulses (halos, rings) are Web Animations that
 * neither one reaches. This cancels them. Spinners (`.animate-spin`) and
 * anything inside `[data-motion-essential]` stay: they are the only sign that
 * work is in progress.
 */
const ESSENTIAL = '.animate-spin, [data-motion-essential]';

export function cancelDecorativeLoops(doc: Document): number {
  if (typeof doc.getAnimations !== 'function') return 0;
  let cancelled = 0;
  for (const animation of doc.getAnimations()) {
    const timing = animation.effect?.getComputedTiming();
    if (!timing || timing.iterations !== Infinity) continue;
    const target = (animation.effect as KeyframeEffect | null)?.target;
    if (target?.closest?.(ESSENTIAL)) continue;
    animation.cancel();
    cancelled += 1;
  }
  return cancelled;
}

/** Install once at app start. Returns a cleanup function. */
export function installReducedMotionGuard(win: Window = window): () => void {
  if (typeof win.matchMedia !== 'function') return () => undefined;
  const query = win.matchMedia('(prefers-reduced-motion: reduce)');
  let timer: ReturnType<typeof setTimeout> | undefined;
  let observer: MutationObserver | undefined;

  const schedule = () => {
    if (timer !== undefined) return;
    timer = setTimeout(() => {
      timer = undefined;
      if (query.matches) cancelDecorativeLoops(win.document);
    }, 250);
  };
  const start = () => {
    if (!query.matches || observer) return;
    observer = new MutationObserver(schedule);
    observer.observe(win.document.body, { childList: true, subtree: true });
    schedule();
  };
  const onChange = () => {
    if (query.matches) start();
    else {
      observer?.disconnect();
      observer = undefined;
    }
  };

  start();
  query.addEventListener?.('change', onChange);
  return () => {
    observer?.disconnect();
    if (timer !== undefined) clearTimeout(timer);
    query.removeEventListener?.('change', onChange);
  };
}
