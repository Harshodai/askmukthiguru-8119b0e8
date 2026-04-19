import { useCallback, useEffect, useState } from 'react';
import {
  FAVORITES_EVENT,
  loadFavorites,
  toggleFavorite as persistToggle,
} from '@/lib/favoritesStorage';

/**
 * Reactive hook for favorited practice slugs.
 * Listens to cross-component updates via `favorites:updated`.
 */
export const useFavorites = () => {
  const [favorites, setFavorites] = useState<string[]>(() => loadFavorites());

  useEffect(() => {
    const handler = () => setFavorites(loadFavorites());
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

  return { favorites, toggle, isFavorited };
};
