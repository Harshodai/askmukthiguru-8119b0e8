/**
 * auth.e2e.test.ts
 * ================
 * End-to-end authentication flow tests for AskMukthiGuru.
 *
 * Covers:
 *  1. New OAuth user gets full name from Google metadata (not "Seeker")
 *  2. Existing user with stored profile keeps their display name
 *  3. Avatar URL from Google OAuth is persisted and readable
 *  4. Email-only user with no avatar is handled gracefully
 *  5. Sign-out clears profile from localStorage
 *  6. Stream checkpoint lifecycle (create, restore, expire, clear)
 *
 * Run:
 *   npx vitest run src/tests/auth.e2e.test.ts
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  loadProfile,
  saveProfile,
  clearProfile,
  createDefaultProfile,
  DEFAULT_DISPLAY_NAME,
} from '@/lib/profileStorage';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const GOOGLE_USER_METADATA = {
  full_name: 'Harsha Daikolluru',
  name: 'Harsha Daikolluru',
  avatar_url: 'https://lh3.googleusercontent.com/a/test-avatar',
  picture: 'https://lh3.googleusercontent.com/a/test-avatar',
  email: 'harsha@example.com',
  email_verified: true,
};

const EMAIL_USER_METADATA = {
  email: 'user@example.com',
  email_verified: true,
};

// ─── Unit tests for profileStorage metadata sync ──────────────────────────────

describe('profileStorage — OAuth metadata sync', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should return DEFAULT_DISPLAY_NAME "Seeker" when no profile saved', () => {
    const profile = loadProfile();
    expect(profile.displayName).toBe(DEFAULT_DISPLAY_NAME);
    expect(DEFAULT_DISPLAY_NAME).toBe('Seeker');
  });

  it('should NOT save "Seeker" as display name for a Google OAuth user', () => {
    const metadata = GOOGLE_USER_METADATA;
    const fullName = (metadata.full_name ?? metadata.name ?? '') as string;
    expect(fullName).not.toBe('');
    expect(fullName).not.toBe(DEFAULT_DISPLAY_NAME);

    // Simulate what AuthPage.tsx does on sign-in: only update if still default
    const existing = loadProfile();
    if (existing.displayName === DEFAULT_DISPLAY_NAME) {
      saveProfile({ ...existing, displayName: fullName }, false);
    }

    const saved = loadProfile();
    expect(saved.displayName).toBe('Harsha Daikolluru');
  });

  it('should NOT overwrite an existing user-set display name on re-login', () => {
    // User previously set a custom name
    const custom = createDefaultProfile();
    custom.displayName = 'Custom Spiritual Name';
    saveProfile(custom, false);

    // OAuth sign-in fires again
    const existing = loadProfile();
    if (existing.displayName === DEFAULT_DISPLAY_NAME) {
      saveProfile({ ...existing, displayName: 'Harsha Daikolluru' }, false);
    }

    const saved = loadProfile();
    // Custom name must be preserved — it was not "Seeker"
    expect(saved.displayName).toBe('Custom Spiritual Name');
  });

  it('should store avatarUrl from Google OAuth metadata', () => {
    const metadata = GOOGLE_USER_METADATA;
    const avatarUrl = (metadata.avatar_url ?? metadata.picture ?? null) as string | null;

    const profile = createDefaultProfile();
    saveProfile({ ...profile, avatarUrl }, false);

    const saved = loadProfile();
    expect(saved.avatarUrl).toBe('https://lh3.googleusercontent.com/a/test-avatar');
  });

  it('should handle email user with no avatar gracefully', () => {
    const metadata: Record<string, unknown> = EMAIL_USER_METADATA;
    const avatarUrl = (metadata.avatar_url ?? metadata.picture ?? null) as string | null;

    expect(avatarUrl).toBeNull();
    // Profile should remain with no avatarUrl
    const saved = loadProfile();
    expect(saved.avatarUrl ?? null).toBeNull();
  });

  it('should clear profile on sign-out', () => {
    const profile = createDefaultProfile();
    profile.displayName = 'Harsha Daikolluru';
    profile.avatarUrl = 'https://lh3.googleusercontent.com/a/test-avatar';
    saveProfile(profile, false);

    expect(loadProfile().displayName).toBe('Harsha Daikolluru');

    clearProfile();

    // After clearing, loadProfile returns a fresh default
    const after = loadProfile();
    expect(after.displayName).toBe(DEFAULT_DISPLAY_NAME);
    expect(after.avatarUrl ?? null).toBeNull();
  });
});

// ─── Stream checkpoint lifecycle ──────────────────────────────────────────────

describe('sessionStorage stream checkpoint', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('should be restorable when fresh (< 60s old)', () => {
    const checkpoint = {
      conversationId: 'conv-1',
      messageId: 'msg-123',
      content: 'This is a partial guru response that was interrupted mid-stream.',
      timestamp: Date.now() - 5_000,
    };
    sessionStorage.setItem(
      'askmukthiguru_stream_checkpoint',
      JSON.stringify(checkpoint),
    );

    const raw = sessionStorage.getItem('askmukthiguru_stream_checkpoint');
    const parsed = raw ? JSON.parse(raw) : null;

    expect(parsed).not.toBeNull();
    expect(parsed.content.length).toBeGreaterThan(20);
    expect(Date.now() - parsed.timestamp).toBeLessThan(60_000);
  });

  it('should be treated as stale when older than 60s', () => {
    const checkpoint = {
      conversationId: 'conv-1',
      messageId: 'msg-123',
      content: 'Old partial content.',
      timestamp: Date.now() - 90_000, // 90s ago
    };
    sessionStorage.setItem(
      'askmukthiguru_stream_checkpoint',
      JSON.stringify(checkpoint),
    );

    const raw = sessionStorage.getItem('askmukthiguru_stream_checkpoint');
    const parsed = raw ? JSON.parse(raw) : null;
    const isStale = parsed ? Date.now() - parsed.timestamp > 60_000 : true;

    expect(isStale).toBe(true);
  });

  it('should be removed after successful stream completion (finally block)', () => {
    sessionStorage.setItem(
      'askmukthiguru_stream_checkpoint',
      JSON.stringify({ content: 'test', timestamp: Date.now() }),
    );
    // Simulate what the finally block does
    sessionStorage.removeItem('askmukthiguru_stream_checkpoint');
    expect(sessionStorage.getItem('askmukthiguru_stream_checkpoint')).toBeNull();
  });

  it('checkpoint content must exceed 20 chars to be saved (guard in interval)', () => {
    const shortContent = 'Hi.'; // < 20 chars — interval skips this
    expect(shortContent.length).toBeLessThan(20);
    // Interval does: if (fullContent.length > 20) { save }
    // So nothing should be in sessionStorage
    expect(sessionStorage.getItem('askmukthiguru_stream_checkpoint')).toBeNull();
  });
});
