import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const TRANSLATIONS: Record<string, string> = {
  'chat.engagement.didThisLand': 'Did this land?',
  'chat.engagement.yes': 'Yes',
  'chat.engagement.notQuite': 'Not quite',
  'chat.engagement.thanks': 'Thanks',
  'chat.clearAnswer': 'Clear answer',
  'chat.relevantSources': 'Relevant sources',
  'chat.calmingTone': 'Calming tone',
  'chat.insightful': 'Insightful',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => TRANSLATIONS[key] ?? key }),
}));

vi.mock('@/lib/chatStorage', () => ({
  saveFeedback: vi.fn(),
  isIncognitoMode: vi.fn().mockReturnValue(false),
}));

vi.mock('@/lib/chat', () => ({
  submitFeedbackToBackend: vi.fn().mockResolvedValue(undefined),
}));

import { EngagementCard } from '@/components/chat/InlineActions';
import { submitFeedbackToBackend } from '@/lib/chat';

describe('EngagementCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderCard = (props = {}) =>
    render(
      <EngagementCard
        messageId="msg-001"
        messageContent="Test answer"
        queryText="What is truth?"
        {...props}
      />,
    );

  it('renders prompt text', () => {
    renderCard();
    expect(screen.getByText('Did this land?')).toBeInTheDocument();
  });

  it('renders Yes and Not quite buttons', () => {
    renderCard();
    expect(screen.getByTestId('engagement-yes')).toBeInTheDocument();
    expect(screen.getByTestId('engagement-not-quite')).toBeInTheDocument();
  });

  it('fires feedback with rating=1 on Yes', async () => {
    renderCard();
    fireEvent.click(screen.getByTestId('engagement-yes'));
    await waitFor(() => expect(submitFeedbackToBackend).toHaveBeenCalledTimes(1));
    expect(submitFeedbackToBackend).toHaveBeenCalledWith(
      expect.objectContaining({ rating: 1, answer: 'Test answer', query: 'What is truth?' }),
    );
  });

  it('shows thanks state after Yes click', async () => {
    renderCard();
    fireEvent.click(screen.getByTestId('engagement-yes'));
    await waitFor(() => expect(screen.getByTestId('engagement-thanks')).toBeInTheDocument());
    expect(screen.queryByTestId('engagement-yes')).not.toBeInTheDocument();
  });

  it('opens refine panel after Not quite click', async () => {
    renderCard();
    fireEvent.click(screen.getByTestId('engagement-not-quite'));
    await waitFor(() => expect(screen.getByText('Clear answer')).toBeInTheDocument());
  });
});
