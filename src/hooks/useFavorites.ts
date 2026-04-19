import { useCallback, useEffect, useState } from 'react';
import {
  FAVORITES_EVENT,
  loadFavorites,
  loadRecentPractice,
  toggleFavorite as persistToggle,
} from '@/lib/favoritesStorage';

/**
 * Reactive hook for favorited practice slugs and the most recent practice.
 * Listens to cross-component updates via `favorites:updated`.
 */
export const useFavorites = () => {
  const [favorites, setFavorites] = useState<string[]>(() => loadFavorites());
  const [recent, setRecent] = useState<string | null>(() => loadRecentPractice());

  useEffect(() => {
    const handler = () => {
      setFavorites(loadFavorites());
      setRecent(loadRecentPractice());
    };
    window.addEventListener(FAVORITES_EVENT, handler);
    window.addEventListener('storage', handler);
    return () => {
      window.removeEventListener(FAVORITES_EVENT, handler);
      window.removeEventListener('storage', handler);
    };
  }, []);

  const toggle = useCallback((slug: string) => {
    const nowFavorited = persistToggle(slug);
    setFavorites(loadFavorites());
    return nowFavorited;
  }, []);

  const isFavorited = useCallback(
    (slug: string) => favorites.includes(slug),
    [favorites],
  );

  return { favorites, recent, toggle, isFavorited };
};
