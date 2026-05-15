import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CookieConsentBanner, getConsent } from '@/components/common/CookieConsentBanner';
import { MemoryRouter } from 'react-router-dom';

beforeEach(() => {
  localStorage.clear();
});

describe('CookieConsentBanner', () => {
  it('shows banner when no consent stored, then hides on accept', async () => {
    render(
      <MemoryRouter>
        <CookieConsentBanner />
      </MemoryRouter>,
    );
    const accept = await screen.findByText('Accept all', {}, { timeout: 2000 });
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
    expect(screen.queryByText('Accept all')).toBeNull();
  });
});
