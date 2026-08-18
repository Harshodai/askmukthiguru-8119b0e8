import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AiTransparencyBanner } from '@/components/compliance/AiTransparencyBanner';

describe('AiTransparencyBanner Component', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('renders EU AI Act Article 50(1) notification text when not dismissed', () => {
    render(<AiTransparencyBanner persistent={true} />);

    const banner = screen.getByTestId('ai-transparency-banner');
    expect(banner).toBeInTheDocument();
    expect(
      screen.getByText(/You are conversing with AskMukthiGuru AI, an artificial intelligence assistant/i)
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /article 50 notice/i })).toBeInTheDocument();
  });

  it('dismisses when close button is clicked and triggers callback', () => {
    const handleDismiss = vi.fn();
    render(<AiTransparencyBanner persistent={true} onDismiss={handleDismiss} />);

    const dismissBtn = screen.getByRole('button', { name: /dismiss ai transparency notice/i });
    expect(dismissBtn).toBeInTheDocument();

    fireEvent.click(dismissBtn);

    expect(screen.queryByTestId('ai-transparency-banner')).not.toBeInTheDocument();
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('opens ProvenanceDrawer when "Article 50 Notice" is clicked', () => {
    render(<AiTransparencyBanner persistent={true} />);

    const noticeBtn = screen.getByRole('button', { name: /article 50 notice/i });
    fireEvent.click(noticeBtn);

    expect(screen.getByTestId('provenance-drawer')).toBeInTheDocument();
    expect(screen.getByText('AI Provenance & Disclosure')).toBeInTheDocument();
  });
});
