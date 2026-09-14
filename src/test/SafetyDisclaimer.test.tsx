import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SafetyDisclaimer } from '@/components/common/SafetyDisclaimer';

// SafetyDisclaimer had zero renderers anywhere in the app until it was wired
// into App.tsx alongside CookieConsentBanner — no test existed either.

beforeEach(() => {
  localStorage.clear();
});

describe('SafetyDisclaimer', () => {
  it('shows on first visit and persists acceptance', async () => {
    render(<SafetyDisclaimer />);
    const accept = await screen.findByText(/Begin My Journey/i, {}, { timeout: 2000 });
    fireEvent.click(accept);
    expect(localStorage.getItem('askmukthiguru_disclaimer_accepted')).toBe('true');
  });

  it('does not show when acceptance already stored', () => {
    localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
    render(<SafetyDisclaimer />);
    expect(screen.queryByText(/Begin My Journey/i)).toBeNull();
  });
});
