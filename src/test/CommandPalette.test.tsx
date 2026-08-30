import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CommandPalette } from '@/components/common/CommandPalette';
import { SereneMindProvider } from '@/components/common/SereneMindProvider';
import * as chatStorage from '@/lib/chatStorage';

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when open is false', () => {
    const { container } = render(
      <SereneMindProvider>
        <CommandPalette open={false} onOpenChange={vi.fn()} onNavigate={vi.fn()} />
      </SereneMindProvider>
    );
    expect(screen.queryByPlaceholderText(/Search AskMukthiGuru/i)).not.toBeInTheDocument();
  });

  it('renders search input and workspace navigation items when open', async () => {
    const now = new Date();
    vi.spyOn(chatStorage, 'loadConversations').mockResolvedValue([
      {
        id: 'c1',
        preview: 'How do I reach the beautiful state?',
        messageCount: 4,
        startedAt: now,
        updatedAt: now,
        messages: [],
      },
    ]);

    render(
      <SereneMindProvider>
        <CommandPalette open={true} onOpenChange={vi.fn()} onNavigate={vi.fn()} />
      </SereneMindProvider>
    );

    expect(screen.getByPlaceholderText(/Search AskMukthiGuru/i)).toBeInTheDocument();
    expect(screen.getByText(/Start Serene Mind meditation/i)).toBeInTheDocument();
    expect(screen.getByText(/Chat with the Gurus/i)).toBeInTheDocument();
    expect(screen.getByText(/Wisdom Map/i)).toBeInTheDocument();
    expect(screen.getByText(/My Reflections/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/How do I reach the beautiful state\?/i)).toBeInTheDocument();
    });
  });

  it('invokes onNavigate and closes when a navigation item is selected', async () => {
    const onNavigate = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <SereneMindProvider>
        <CommandPalette open={true} onOpenChange={onOpenChange} onNavigate={onNavigate} />
      </SereneMindProvider>
    );

    const chatItem = screen.getByText(/Chat with the Gurus/i);
    fireEvent.click(chatItem);

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onNavigate).toHaveBeenCalledWith('/chat');
  });
});
