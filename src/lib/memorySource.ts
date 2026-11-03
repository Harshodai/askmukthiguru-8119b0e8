/**
 * Where a memory or Wisdom Map node came from.
 *
 * The backend returns only `{ kind, id }` when the stored row proves a source,
 * and nothing otherwise. This module is the single place that turns a source
 * into an app route. A kind it does not know, or an id that does not look like
 * one, yields `null` so callers show "source unavailable" instead of a made-up
 * or broken link.
 */

export interface MemorySourceRef {
  kind: string;
  id: string;
}

const SOURCE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;

export function normalizeSourceRef(value: unknown): MemorySourceRef | null {
  if (!value || typeof value !== 'object') return null;
  const { kind, id } = value as { kind?: unknown; id?: unknown };
  if (typeof kind !== 'string' || typeof id !== 'string') return null;
  return SOURCE_ID_PATTERN.test(id) ? { kind, id } : null;
}

/** In-app route for a source, or null when it cannot be linked. */
export function memorySourceHref(ref: MemorySourceRef | null | undefined, returnTo?: string): string | null {
  const source = normalizeSourceRef(ref);
  if (!source) return null;
  switch (source.kind) {
    case 'conversation': {
      const back = returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : '';
      return `/chat?conversation=${encodeURIComponent(source.id)}${back}`;
    }
    case 'notebook':
      // The notebook page has no per-item deep link; link to the notebook itself.
      return '/notebooks';
    default:
      return null;
  }
}

/** Default English label for a linkable source; callers pass it through t(). */
export function memorySourceLabel(ref: MemorySourceRef | null | undefined): string {
  return ref?.kind === 'notebook' ? 'Open study notebook' : 'Open original conversation';
}
