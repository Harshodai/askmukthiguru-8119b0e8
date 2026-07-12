import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const TRANSLATIONS: Record<string, string> = {
  'chat.engagement.didThisHelp': 'Did this help?',
  'chat.engagement.yes': 'Yes',
  'chat.engagement.needsWork': 'Needs work',
  'chat.engagement.no': 'No',
  'chat.engagement.thanks': 'Thanks',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => TRANSLATIONS[key] ?? key }),
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
    render(<EngagementCard messageContent="Test answer" queryText="What is truth?" {...props} />);

  it('renders "Did this help?" prompt', () => {
    renderCard();
    expect(screen.getByText('Did this help?')).toBeInTheDocument();
  });

  it('fires feedback with rating=2 on Yes', async () => {
    renderCard();
    fireEvent.click(screen.getByLabelText('Yes'));
    await waitFor(() => expect(submitFeedbackToBackend).toHaveBeenCalledTimes(1));
    expect(submitFeedbackToBackend).toHaveBeenCalledWith(
      expect.objectContaining({ rating: 2, answer: 'Test answer', query: 'What is truth?' }),
    );
  });

  it('fires feedback with rating=1 on Needs work', async () => {
    renderCard();
    fireEvent.click(screen.getByLabelText('Needs work'));
    await waitFor(() => expect(submitFeedbackToBackend).toHaveBeenCalledWith(expect.objectContaining({ rating: 1 })));
  });

  it('fires feedback with rating=0 on No', async () => {
    renderCard();
    fireEvent.click(screen.getByLabelText('No'));
    await waitFor(() => expect(submitFeedbackToBackend).toHaveBeenCalledWith(expect.objectContaining({ rating: 0 })));
  });

  it('collapses to Thanks after click', async () => {
    renderCard();
    fireEvent.click(screen.getByLabelText('Yes'));
    await waitFor(() => expect(screen.getByText('Thanks')).toBeInTheDocument());
    expect(screen.queryByLabelText('Yes')).not.toBeInTheDocument();
  });
});
