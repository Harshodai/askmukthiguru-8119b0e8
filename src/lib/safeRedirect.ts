/**
 * Same-origin relative-path predicate for post-auth redirects.
 *
 * The stored redirect (sessionStorage / `?intended=`) is attacker-writable (XSS or a
 * crafted link), so it must be a same-origin relative path before we navigate to it.
 * One definition shared by every auth page — the three inline copies had to be edited in
 * lockstep and could drift.
 */
export const isSafeRelativePath = (url: string | null | undefined): url is string =>
  Boolean(
    url &&
    url.startsWith('/') &&
    !url.startsWith('//') &&
    !url.startsWith('/@') &&
    !url.includes('\\') &&
    !url.includes('@') &&
    !url.includes('://')
  );
