import { beforeEach, describe, expect, it, vi } from 'vitest';

const { rpcMock } = vi.hoisted(() => ({ rpcMock: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { rpc: rpcMock },
}));

import {
  LAUNCH_SIGNUP_SOURCES,
  isPlausibleLaunchEmail,
  sanitizeLaunchEmail,
  submitLaunchSignup,
} from '@/lib/launchUpdates';

describe('launch updates intake', () => {
  beforeEach(() => {
    rpcMock.mockReset();
  });

  it('normalizes surrounding whitespace and case', () => {
    expect(sanitizeLaunchEmail('  Seeker@Example.COM  ')).toBe('seeker@example.com');
  });

  it('bounds the address at 254 characters', () => {
    const long = `${'a'.repeat(300)}@example.com`;
    expect(sanitizeLaunchEmail(long)).toHaveLength(254);
    expect(isPlausibleLaunchEmail(long)).toBe(false);
  });

  it('rejects malformed addresses and accepts a plain valid one', () => {
    expect(isPlausibleLaunchEmail('not-an-email')).toBe(false);
    expect(isPlausibleLaunchEmail('a@b')).toBe(false);
    expect(isPlausibleLaunchEmail('seeker@example.com')).toBe(true);
  });

  it('sends normalized email, source and explicit consent', async () => {
    rpcMock.mockResolvedValue({ data: 'accepted', error: null });

    await expect(
      submitLaunchSignup({ email: '  Seeker@Example.com ', source: 'guide_serene_mind' }),
    ).resolves.toEqual({ status: 'accepted' });

    expect(rpcMock).toHaveBeenCalledWith('subscribe_launch_updates', {
      p_email: 'seeker@example.com',
      p_consent: true,
      p_source: 'guide_serene_mind',
    });
  });

  it('never echoes the address in a success or failure result', async () => {
    rpcMock.mockResolvedValueOnce({ data: 'accepted', error: null });
    const accepted = await submitLaunchSignup({
      email: 'seeker@example.com',
      source: 'guide_ai_spiritual_companion',
    });
    expect(JSON.stringify(accepted)).not.toContain('seeker@example.com');

    rpcMock.mockResolvedValueOnce({ data: null, error: { message: 'Signup temporarily busy' } });
    const failed = await submitLaunchSignup({
      email: 'seeker@example.com',
      source: 'guide_ai_spiritual_companion',
    });
    expect(failed).toEqual({ status: 'failed', reason: 'request_failed' });
    expect(JSON.stringify(failed)).not.toContain('seeker@example.com');
  });

  it('does not call the database for an obviously invalid address', async () => {
    const result = await submitLaunchSignup({
      email: 'nope',
      source: 'guide_ai_spiritual_companion',
    });
    expect(result).toEqual({ status: 'failed', reason: 'invalid_email' });
    expect(rpcMock).not.toHaveBeenCalled();
  });

  it('uses only sources the database accepts', () => {
    expect(LAUNCH_SIGNUP_SOURCES).toEqual([
      'guide_ai_spiritual_companion',
      'guide_serene_mind',
      'guide_spirit_guides',
      'guide_beautiful_state',
      'guide_self_centric',
      'guide_anxiety',
      'guide_suffering',
    ]);
  });
});
