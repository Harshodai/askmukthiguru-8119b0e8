import { describe, expect, it } from 'vitest';
import { isPushPromptEligible } from '@/lib/chat/pushEligibility';

const base = { blocked: false, groundingState: 'grounded', routeDecision: 'first_person_bridge' };

describe('isPushPromptEligible (T1-10)', () => {
  it('allows a grounded teaching answer with no notices', () => {
    expect(isPushPromptEligible({ ...base, safetyNotices: [] })).toBe(true);
  });
  it.each([
    ['blocked', { blocked: true }],
    ['safety_redirect', { groundingState: 'safety_redirect' }],
    ['abstained', { groundingState: 'abstained' }],
    ['abstain flag', { isFirstPersonAbstain: true }],
    ['crisis route', { routeDecision: 'crisis_helpline' }],
    ['no route', { routeDecision: null }],
    ['safety notice', { safetyNotices: ['relationship_boundary'] }],
    ['distress signal', { proactiveSereneMind: { level: 'MODERATE' } }],
  ])('refuses: %s', (_n, patch) => {
    expect(isPushPromptEligible({ ...base, ...patch })).toBe(false);
  });
});
