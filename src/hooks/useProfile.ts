import { useEffect, useState, useCallback } from 'react';
import {
  UserProfile,
  loadProfile,
  saveProfile,
  updateProfile as persistUpdate,
} from '@/lib/profileStorage';

/**
 * Reactive hook for the local user profile.
 * Listens to cross-component updates via the `profile:updated` event.
 */
export const useProfile = () => {
  const [profile, setProfile] = useState<UserProfile>(() => loadProfile());

  useEffect(() => {
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

  return { profile, update, replace };
};
