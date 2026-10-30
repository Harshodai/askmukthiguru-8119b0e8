/** Window in which an identical typed send counts as an accidental repeat. */
export const DUPLICATE_SUBMIT_WINDOW_MS = 800;

/**
 * True when `text` repeats the previous typed send inside the window.
 * Compares trimmed text so trailing whitespace from key repeat does not slip past.
 */
export const isDuplicateSubmit = (
  last: { text: string; at: number } | null,
  text: string,
  now: number,
  windowMs: number = DUPLICATE_SUBMIT_WINDOW_MS,
): boolean => !!last && last.text.trim() === text.trim() && now - last.at < windowMs;

export type SubmitDecision =
  | 'empty'
  | 'blocked_context'
  | 'blocked_quota'
  | 'queue'
  | 'interrupt'
  | 'send';

/**
 * What a send attempt should do. Refusals (`blocked_*`) are decided BEFORE
 * `interrupt`, so a send that cannot start never aborts the answer being read.
 */
export const decideSubmit = (input: {
  text: string;
  active: boolean;
  forceImmediate: boolean;
  contextExhausted: boolean;
  quotaExceeded: boolean;
}): SubmitDecision => {
  if (!input.text.trim()) return 'empty';
  if (input.contextExhausted) return 'blocked_context';
  if (input.quotaExceeded) return 'blocked_quota';
  if (input.active) return input.forceImmediate ? 'interrupt' : 'queue';
  return 'send';
};

/**
 * Files for one turn. An explicit override, even an empty list, wins: a drained
 * queued turn must not pick up files attached to a later draft.
 */
export const resolveTurnFiles = <T>(override: T[] | undefined, current: T[]): T[] =>
  override !== undefined ? override : current;
