import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadProfile,
  saveProfile,
  updateProfile,
  resetProfile,
  createDefaultProfile,
  exportAllData,
  deleteAllData,
  getInitials,
} from '@/lib/profileStorage';

describe('profileStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('creates a default profile when none exists', () => {
    const profile = loadProfile();
    expect(profile.displayName).toBe('Seeker');
    expect(profile.preferredLanguage).toBe('en');
    expect(profile.guruTone).toBe('gentle');
    expect(profile.avatarDataUrl).toBeNull();
  });

  it('persists and reloads profile updates', () => {
    const next = updateProfile({ displayName: 'Arjuna', preferredLanguage: 'hi' });
    expect(next.displayName).toBe('Arjuna');
    const reloaded = loadProfile();
    expect(reloaded.displayName).toBe('Arjuna');
    expect(reloaded.preferredLanguage).toBe('hi');
  });

  it('saveProfile dispatches profile:updated event', () => {
    const handler = vi.fn();
    window.addEventListener('profile:updated', handler);
    saveProfile({ ...createDefaultProfile(), displayName: 'Sita' });
    expect(handler).toHaveBeenCalled();
    window.removeEventListener('profile:updated', handler);
  });

  it('resetProfile produces a fresh seeker', () => {
    updateProfile({ displayName: 'Krishna' });
    const fresh = resetProfile();
    expect(fresh.displayName).toBe('Seeker');
  });

  it('exportAllData includes profile, conversations, sessions', () => {
    updateProfile({ displayName: 'Maya' });
    const data = exportAllData();
    expect(data.profile.displayName).toBe('Maya');
    expect(Array.isArray(data.conversations)).toBe(true);
    expect(Array.isArray(data.meditationSessions)).toBe(true);
    expect(data.version).toBe(1);
  });

  it('deleteAllData clears all relevant keys', () => {
    localStorage.setItem('askmukthiguru_conversations', '[1]');
    localStorage.setItem('askmukthiguru_meditation_sessions', '[1]');
    updateProfile({ displayName: 'Indra' });
    deleteAllData();
    expect(localStorage.getItem('askmukthiguru_profile')).toBeNull();
    expect(localStorage.getItem('askmukthiguru_conversations')).toBeNull();
    expect(localStorage.getItem('askmukthiguru_meditation_sessions')).toBeNull();
  });

  describe('getInitials', () => {
    it('returns first letter for single name', () => {
      expect(getInitials('Arjuna')).toBe('AR');
    });
    it('returns first + last initial for multi-word names', () => {
      expect(getInitials('Sri Krishnaji')).toBe('SK');
    });
    it('falls back to S for empty input', () => {
      expect(getInitials('')).toBe('S');
    });
  });
});

// vi global
import { vi } from 'vitest';
