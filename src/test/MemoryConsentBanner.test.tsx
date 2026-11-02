import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryConsentBanner, MEMORY_BANNER_DISMISSED_KEY } from '@/components/chat/MemoryConsentBanner';
import { memoryApi } from '@/lib/memoryApi';

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: {
    recordConsent: vi.fn().mockResolvedValue(undefined),
  },
  MemoryApiError: class extends Error {},
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe('MemoryConsentBanner', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('does not render when user is unauthenticated', () => {
    render(
      <MemoryConsentBanner
        isAuthenticated={false}
        isIncognito={false}
        hasConsent={false}
        onConsentChange={vi.fn()}
      />
    );
    expect(screen.queryByTestId('memory-consent-banner')).toBeNull();
  });

  it('does not render when in incognito mode', () => {
    render(
      <MemoryConsentBanner
        isAuthenticated={true}
        isIncognito={true}
        hasConsent={false}
        onConsentChange={vi.fn()}
      />
    );
    expect(screen.queryByTestId('memory-consent-banner')).toBeNull();
  });

  it('does not render when memory consent is already granted', () => {
    render(
      <MemoryConsentBanner
        isAuthenticated={true}
        isIncognito={false}
        hasConsent={true}
        onConsentChange={vi.fn()}
      />
    );
    expect(screen.queryByTestId('memory-consent-banner')).toBeNull();
  });

  it('does not render when previously dismissed in localStorage', () => {
    localStorage.setItem(MEMORY_BANNER_DISMISSED_KEY, '1');
    render(
      <MemoryConsentBanner
        isAuthenticated={true}
        isIncognito={false}
        hasConsent={false}
        onConsentChange={vi.fn()}
      />
    );
    expect(screen.queryByTestId('memory-consent-banner')).toBeNull();
  });

  it('renders correctly when authenticated, not incognito, and consent ungranted', () => {
    render(
      <MemoryConsentBanner
        isAuthenticated={true}
        isIncognito={false}
        hasConsent={false}
        onConsentChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('memory-consent-banner')).toBeInTheDocument();
    expect(screen.getByTestId('enable-memory-button')).toBeInTheDocument();
    expect(screen.getByTestId('dismiss-memory-banner-button')).toBeInTheDocument();
  });

  it('calls memoryApi.recordConsent(true) and onConsentChange(true) when enabled', async () => {
    const onConsentChange = vi.fn();
    render(
      <MemoryConsentBanner
        isAuthenticated={true}
        isIncognito={false}
        hasConsent={false}
        onConsentChange={onConsentChange}
      />
    );

    const enableBtn = screen.getByTestId('enable-memory-button');
    fireEvent.click(enableBtn);

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(true);
      expect(onConsentChange).toHaveBeenCalledWith(true);
      expect(localStorage.getItem(MEMORY_BANNER_DISMISSED_KEY)).toBeNull();
    });
  });

  it('persists dismissal in localStorage when dismissed', () => {
    render(
      <MemoryConsentBanner
        isAuthenticated={true}
        isIncognito={false}
        hasConsent={false}
        onConsentChange={vi.fn()}
      />
    );

    const dismissBtn = screen.getByTestId('dismiss-memory-banner-button');
    fireEvent.click(dismissBtn);

    expect(localStorage.getItem(MEMORY_BANNER_DISMISSED_KEY)).toBe('1');
    expect(screen.queryByTestId('memory-consent-banner')).toBeNull();
  });
});
