import { useEffect, useState, useCallback } from 'react';
import {
  UserProfile,
  loadProfile,
  saveProfile,
  updateProfile as persistUpdate,
  fetchProfileFromServer,
} from '@/lib/profileStorage';

/**
 * Reactive hook for the local user profile.
 * Listens to cross-component updates via the `profile:updated` event.
 */
export const useProfile = () => {
  const [profile, setProfile] = useState<UserProfile>(() => loadProfile());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Initial fetch/sync from server. fetchProfileFromServer may write
    // auth metadata (full_name, avatar_url) to localStorage as a side effect.
    // We always re-read from loadProfile() afterwards to pick up those writes.
    const sync = async () => {
      try {
        await fetchProfileFromServer();
        setProfile(loadProfile());
      } catch (err) {
        console.error('Error syncing profile on load:', err);
      } finally {
        setLoading(false);
      }
    };
    sync();

    const handler = () => setProfile(loadProfile());
    window.addEventListener('profile:updated', handler);
    window.addEventListener('storage', handler);
    return () => {
      window.removeEventListener('profile:updated', handler);
      window.removeEventListener('storage', handler);
    };
  }, []);

  const update = useCallback((patch: Partial<UserProfile>) => {
    const next = persistUpdate(patch);
    setProfile(next);
    return next;
  }, []);

  const replace = useCallback((next: UserProfile) => {
    saveProfile(next);
    setProfile(next);
  }, []);

  return { profile, loading, update, replace };
};
