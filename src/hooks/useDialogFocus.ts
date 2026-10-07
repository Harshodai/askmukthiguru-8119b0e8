import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface DialogFocusOptions {
  /** Element to focus on open. Defaults to the first focusable in the dialog. */
  initialFocus?: RefObject<HTMLElement | null>;
  /** Called on Escape. Omit for dialogs that must not close on Escape. */
  onEscape?: () => void;
}

/**
 * Modal keyboard contract for hand-rolled dialogs (ones not built on the
 * Radix `Dialog` primitive, which already does this):
 *
 * - focus moves into the dialog when it opens,
 * - Tab and Shift+Tab stay inside it,
 * - Escape calls `onEscape` when given,
 * - focus returns to whatever had it before the dialog opened.
 *
 * Ten dialogs in this app set `aria-modal="true"` but let Tab walk out into the
 * page behind them, so a keyboard or screen-reader user lost the dialog they
 * were told was modal. One hook, so the contract cannot drift per dialog.
 */
export function useDialogFocus<T extends HTMLElement>(
  open: boolean,
  { initialFocus, onEscape }: DialogFocusOptions = {},
): RefObject<T> {
  const containerRef = useRef<T>(null);
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = () =>
      Array.from(containerRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
        (el) => !el.hasAttribute('aria-hidden'),
      );

    // Wait a frame: dialogs animate in and may not be mounted yet.
    const raf = requestAnimationFrame(() => {
      (initialFocus?.current ?? focusables()[0] ?? containerRef.current)?.focus();
    });

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onEscapeRef.current) {
        e.stopPropagation();
        onEscapeRef.current();
        return;
      }
      if (e.key !== 'Tab' || !containerRef.current) return;
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const inside = containerRef.current.contains(active);
      if (e.shiftKey && (active === first || !inside)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !inside)) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKeyDown, true);
      if (previouslyFocused && document.contains(previouslyFocused)) previouslyFocused.focus();
    };
  }, [open, initialFocus]);

  return containerRef;
}
