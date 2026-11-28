import { describe, it, expect } from 'vitest';
import { validSignup, unsubscribeLink } from '../../supabase/functions/launch-signup/email';

describe('launch email security rules', () => {
  it('requires explicit consent including on the launch page', () => {
    expect(validSignup({ email: 'seeker@example.com', source: 'launch_page', consent: true })).toBe(true);
    expect(validSignup({ email: 'seeker@example.com', source: 'launch_page', consent: false })).toBe(false);
    expect(validSignup({ email: 'seeker@example.com', source: 'launch_page' })).toBe(false);
  });
  it('refuses unknown sources and oversized addresses', () => {
    expect(validSignup({ email: 'seeker@example.com', source: 'unapproved', consent: true })).toBe(false);
    expect(validSignup({ email: `${'a'.repeat(254)}@example.com`, source: 'launch_page', consent: true })).toBe(false);
  });
  it('keeps private unsubscribe credentials out of request URLs and rejects invalid tokens', () => {
    const link = new URL(unsubscribeLink('seeker+test@example.com', '11111111-1111-1111-1111-111111111111'));
    expect(link.origin).toBe('https://askmukthiguru.lovable.app');
    expect(link.pathname).toBe('/unsubscribe');
    expect(link.search).toBe('');
    expect(new URLSearchParams(link.hash.slice(1)).get('email')).toBe('seeker+test@example.com');
    expect(() => unsubscribeLink('seeker@example.com', 'guessable')).toThrow();
  });
});
