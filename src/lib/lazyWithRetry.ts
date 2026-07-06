import { lazy, type ComponentType } from 'react';

const RELOAD_FLAG = 'chunk_reload_attempted';

/**
 * React.lazy wrapper that reloads once on a failed dynamic import.
 * Vite/Rollup chunk URLs are content-hashed, so after a new deploy an
 * already-open tab can request an old chunk the server no longer has —
 * that's a signal to refresh, not a bug worth surfacing as a crash.
 */
export function lazyWithRetry<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>
) {
  return lazy(async () => {
    try {
      const module = await factory();
      sessionStorage.removeItem(RELOAD_FLAG);
      return module;
    } catch (error) {
      if (!sessionStorage.getItem(RELOAD_FLAG)) {
        sessionStorage.setItem(RELOAD_FLAG, '1');
        window.location.reload();
        return new Promise<{ default: T }>(() => {}); // reload takes over
      }
      throw error;
    }
  });
}
