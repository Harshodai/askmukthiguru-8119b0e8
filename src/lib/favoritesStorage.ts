/**
 * Favorites + recents storage for practices.
 * Stores starred practice slugs and the last-opened practice slug locally
 * and broadcasts changes via the `favorites:updated` event so all
 * consumers stay in sync.
 */

const FAVORITES_KEY = 'askmukthiguru_favorite_practices';
const RECENT_KEY = 'askmukthiguru_recent_practice';
const EVENT = 'favorites:updated';

export const loadFavorites = (): string[] => {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((s) => typeof s === 'string') : [];
  } catch {
    return [];
  }
};

export const saveFavorites = (slugs: string[]): void => {
  try {
    const unique = Array.from(new Set(slugs));
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(unique));
    window.dispatchEvent(new CustomEvent(EVENT, { detail: unique }));
  } catch (err) {
    console.error('Failed to save favorites', err);
  }
};

export const isFavorite = (slug: string): boolean => loadFavorites().includes(slug);

export const toggleFavorite = (slug: string): boolean => {
  const current = loadFavorites();
  const exists = current.includes(slug);
  const next = exists ? current.filter((s) => s !== slug) : [...current, slug];
  saveFavorites(next);
  return !exists;
};

/** Track the most recently opened practice slug. */
export const recordRecentPractice = (slug: string): void => {
  try {
    localStorage.setItem(RECENT_KEY, slug);
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch (err) {
    console.error('Failed to save recent practice', err);
  }
};

export const loadRecentPractice = (): string | null => {
  try {
    return localStorage.getItem(RECENT_KEY);
  } catch {
    return null;
  }
};

export const FAVORITES_EVENT = EVENT;
