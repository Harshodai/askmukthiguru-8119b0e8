import { describe, expect, it } from 'vitest';
import { isWaitlistBuildEnabled } from '@/components/landing/WaitlistForm';

describe('isWaitlistBuildEnabled', () => {
  it('is closed unless explicitly enabled at build time', () => {
    expect(isWaitlistBuildEnabled()).toBe(false);
    expect(isWaitlistBuildEnabled('false')).toBe(false);
    expect(isWaitlistBuildEnabled('TRUE')).toBe(true);
    expect(isWaitlistBuildEnabled(' true ')).toBe(true);
  });
});
