import { describe, it, expect, beforeEach } from 'vitest';
import { act, render, screen, fireEvent } from '@testing-library/react';
import { DISCLAIMER_ACCEPTED_EVENT } from '@/components/common/SafetyDisclaimer';
import { CookieConsentBanner, getConsent } from '@/components/common/CookieConsentBanner';
import { MemoryRouter } from 'react-router-dom';

beforeEach(() => {
  localStorage.clear();
});

describe('CookieConsentBanner', () => {
  it('shows banner when no consent stored, then hides on accept', async () => {
    localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
    render(
      <MemoryRouter>
        <CookieConsentBanner />
      </MemoryRouter>,
    );
    const accept = await screen.findByText('Accept', {}, { timeout: 2000 });
    fireEvent.click(accept);
    expect(getConsent()).toBe('accepted');
  });

  it('does not show when consent already stored', () => {
    localStorage.setItem('askmukthiguru_consent_v1', 'rejected');
    render(
      <MemoryRouter>
        <CookieConsentBanner />
      </MemoryRouter>,
    );
    expect(screen.queryByText('Accept')).toBeNull();
  });

  it('waits for the safety notice instead of stacking on it', async () => {
    render(
      <MemoryRouter>
        <CookieConsentBanner />
      </MemoryRouter>,
    );
    await new Promise((r) => setTimeout(r, 1000));
    expect(screen.queryByText('Accept')).toBeNull();
    act(() => {
      localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
      window.dispatchEvent(new Event(DISCLAIMER_ACCEPTED_EVENT));
    });
    expect(await screen.findByText('Accept', {}, { timeout: 2000 })).toBeInTheDocument();
  });
});
