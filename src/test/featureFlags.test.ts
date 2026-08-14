import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('frontend rollout flags', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it('defaults adoption features to enabled', async () => {
    const { FEATURE_FLAGS } = await import('@/lib/featureFlags');
    expect(FEATURE_FLAGS).toEqual({
      wisdomTips: true,
      suggestedFollowUps: true,
      responseProvenance: true,
    });
  });

  it('supports explicit false rollback values', async () => {
    vi.stubEnv('VITE_ENABLE_WISDOM_TIPS', 'false');
    vi.stubEnv('VITE_ENABLE_SUGGESTED_FOLLOWUPS', '0');
    vi.stubEnv('VITE_ENABLE_RESPONSE_PROVENANCE', 'off');
    const { FEATURE_FLAGS } = await import('@/lib/featureFlags');
    expect(FEATURE_FLAGS).toEqual({
      wisdomTips: false,
      suggestedFollowUps: false,
      responseProvenance: false,
    });
  });
});
