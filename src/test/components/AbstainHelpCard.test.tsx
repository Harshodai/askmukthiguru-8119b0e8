import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  AbstainHelpCard,
  ABSTAIN_BANK_QUESTIONS,
  ABSTAIN_OKF_CONCEPTS,
} from '@/components/chat/AbstainHelpCard';

const mockOpenSereneMind = vi.fn();

vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({
    open: mockOpenSereneMind,
    isOpen: false,
    isGated: false,
    close: vi.fn(),
    toggle: vi.fn(),
    onComplete: null,
    setOnComplete: vi.fn(),
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}));

describe('AbstainHelpCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the header, subtitle, 3 verified bank questions, 5 OKF chips, and Serene Mind button', () => {
    render(<AbstainHelpCard />);

    expect(screen.getByTestId('abstain-help-card')).toBeInTheDocument();
    expect(screen.getByText('Explore Verified Teachings')).toBeInTheDocument();
    expect(
      screen.getByText(/While this specific question doesn't have an exact recorded discourse match/i),
    ).toBeInTheDocument();

    // 3 Bank Questions
    ABSTAIN_BANK_QUESTIONS.forEach((q, idx) => {
      const btn = screen.getByTestId(`abstain-question-${idx}`);
      expect(btn).toBeInTheDocument();
      expect(btn).toHaveTextContent(q);
    });

    // 5 OKF Chips
    ABSTAIN_OKF_CONCEPTS.forEach((c, idx) => {
      const chip = screen.getByTestId(`abstain-chip-${idx}`);
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveTextContent(c);
    });

    // Serene Mind Quick-Launch
    const sereneMindBtn = screen.getByTestId('abstain-serene-mind-btn');
    expect(sereneMindBtn).toBeInTheDocument();
    expect(sereneMindBtn).toHaveTextContent('Practice 3-Minute Serene Mind Meditation');
  });

  it('triggers onAction with exact question text when bank questions are clicked', () => {
    const onAction = vi.fn();
    render(<AbstainHelpCard onAction={onAction} />);

    ABSTAIN_BANK_QUESTIONS.forEach((question, idx) => {
      const btn = screen.getByTestId(`abstain-question-${idx}`);
      fireEvent.click(btn);
      expect(onAction).toHaveBeenLastCalledWith(question);
    });

    expect(onAction).toHaveBeenCalledTimes(3);
  });

  it('triggers onAction with exact concept name when OKF chips are clicked', () => {
    const onAction = vi.fn();
    render(<AbstainHelpCard onAction={onAction} />);

    ABSTAIN_OKF_CONCEPTS.forEach((concept, idx) => {
      const chip = screen.getByTestId(`abstain-chip-${idx}`);
      fireEvent.click(chip);
      expect(onAction).toHaveBeenLastCalledWith(concept);
    });

    expect(onAction).toHaveBeenCalledTimes(5);
  });

  it('opens Serene Mind audio modal in gated mode when practice button is clicked', () => {
    render(<AbstainHelpCard />);

    const sereneMindBtn = screen.getByTestId('abstain-serene-mind-btn');
    fireEvent.click(sereneMindBtn);

    expect(mockOpenSereneMind).toHaveBeenCalledWith('audio', true);
  });

  it('handles missing onAction gracefully when clicked', () => {
    render(<AbstainHelpCard />);

    expect(() => {
      fireEvent.click(screen.getByTestId('abstain-question-0'));
      fireEvent.click(screen.getByTestId('abstain-chip-0'));
    }).not.toThrow();
  });
});
