import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemorySettingsModal } from '@/components/chat/MemorySettingsModal';
import { memoryApi } from '@/lib/memoryApi';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: {
    recordConsent: vi.fn().mockResolvedValue(undefined),
    deleteAll: vi.fn().mockResolvedValue(undefined),
  },
  MemoryApiError: class extends Error {},
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe('MemorySettingsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders modal with Active status when hasConsent is true', () => {
    render(
      <MemoryRouter>
        <MemorySettingsModal
          open={true}
          onOpenChange={vi.fn()}
          hasConsent={true}
          onConsentChange={vi.fn()}
        />
      </MemoryRouter>
    );

    expect(screen.getByTestId('memory-settings-modal')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByTestId('toggle-memory-consent-button')).toBeInTheDocument();
  });

  it('toggles memory from Active to Paused', async () => {
    const onConsentChange = vi.fn();
    render(
      <MemoryRouter>
        <MemorySettingsModal
          open={true}
          onOpenChange={vi.fn()}
          hasConsent={true}
          onConsentChange={onConsentChange}
        />
      </MemoryRouter>
    );

    const toggleBtn = screen.getByTestId('toggle-memory-consent-button');
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(false);
      expect(onConsentChange).toHaveBeenCalledWith(false);
    });
  });

  it('toggles memory from Paused to Active', async () => {
    const onConsentChange = vi.fn();
    render(
      <MemoryRouter>
        <MemorySettingsModal
          open={true}
          onOpenChange={vi.fn()}
          hasConsent={false}
          onConsentChange={onConsentChange}
        />
      </MemoryRouter>
    );

    const toggleBtn = screen.getByTestId('toggle-memory-consent-button');
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(true);
      expect(onConsentChange).toHaveBeenCalledWith(true);
    });
  });

  it('opens confirmation and calls deleteAll when erasing memories', async () => {
    const onMemoriesErased = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <MemoryRouter>
        <MemorySettingsModal
          open={true}
          onOpenChange={onOpenChange}
          hasConsent={true}
          onConsentChange={vi.fn()}
          onMemoriesErased={onMemoriesErased}
        />
      </MemoryRouter>
    );

    const eraseBtn = screen.getByTestId('erase-all-memories-button');
    fireEvent.click(eraseBtn);

    const confirmBtn = await screen.findByTestId('confirm-erase-all-button');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(memoryApi.deleteAll).toHaveBeenCalled();
      expect(onMemoriesErased).toHaveBeenCalled();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
