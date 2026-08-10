/**
 * P1-FE-15 unit tests: Serene Mind resume payload is purged on sign-out.
 *
 * The sign-out choke point is the global supabase.auth.signOut monkey-patch in
 * SessionExpiredHandler.tsx (every sign-out path in the app goes through it).
 * Clearing is delegated to clearMeditationResume() from lib/meditationResume
 * so the handler stays lightweight and unit-testable without a component
 * graph. clearProfile() (lib/profileStorage) purges it too.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn().mockResolvedValue({}),
    },
  },
  isEmailAllowed: vi.fn(() => true),
}));

import {
  MEDITATION_RESUME_KEY,
  clearMeditationResume,
} from '@/lib/meditationResume';

const PAYLOAD = JSON.stringify({ sessionId: 'med_1', stepIndex: 3, elapsed: 42, savedAt: Date.now() });

function seedResume(): void {
  localStorage.setItem(MEDITATION_RESUME_KEY, PAYLOAD);
}

describe('clearMeditationResume', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('removes the meditation resume payload from localStorage', () => {
    seedResume();
    expect(localStorage.getItem(MEDITATION_RESUME_KEY)).toBe(PAYLOAD);
    clearMeditationResume();
    expect(localStorage.getItem(MEDITATION_RESUME_KEY)).toBeNull();
  });

  it('is a no-op when nothing is stored', () => {
    expect(() => clearMeditationResume()).not.toThrow();
    expect(localStorage.getItem(MEDITATION_RESUME_KEY)).toBeNull();
  });

  it('does not touch unrelated keys', () => {
    localStorage.setItem('askmukthiguru_profile', '{"displayName":"Seeker"}');
    seedResume();
    clearMeditationResume();
    expect(localStorage.getItem(MEDITATION_RESUME_KEY)).toBeNull();
    expect(localStorage.getItem('askmukthiguru_profile')).not.toBeNull();
  });
});

describe('sign-out purge wiring', () => {
  it('supabase.auth.signOut clears the resume payload before signing out', async () => {
    // Import after mocking so the monkey-patch captures the mocked signOut.
    await import('@/components/common/SessionExpiredHandler');
    const { supabase } = await import('@/integrations/supabase/client');

    seedResume();
    await supabase.auth.signOut();

    expect(localStorage.getItem(MEDITATION_RESUME_KEY)).toBeNull();
  });

  it('clearProfile clears the resume payload', async () => {
    const { clearProfile } = await import('@/lib/profileStorage');
    seedResume();
    clearProfile();
    expect(localStorage.getItem(MEDITATION_RESUME_KEY)).toBeNull();
  });
});
