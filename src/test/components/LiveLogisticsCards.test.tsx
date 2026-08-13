import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LiveLogisticsCards } from '@/components/chat/LiveLogisticsCards';

describe('LiveLogisticsCards', () => {
  it('renders only verified HTTPS official and booking links', () => {
    render(<LiveLogisticsCards events={[
      {
        event_name: 'Oneness gathering',
        official_source_url: 'https://events.example.org/gathering',
        booking_url: 'https://events.example.org/book',
        verified_at: '2026-08-13T10:00:00Z',
        expires_at: '2026-08-13T11:00:00Z',
      },
      {
        event_name: 'Unverified result',
        official_source_url: 'http://untrusted.example.org',
        verified_at: '2026-08-13T10:00:00Z',
        expires_at: '2026-08-13T11:00:00Z',
      },
    ]} />);

    expect(screen.getByRole('region', { name: /verified event and booking/i })).toBeInTheDocument();
    expect(screen.getByText('Oneness gathering')).toBeInTheDocument();
    expect(screen.queryByText('Unverified result')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /official details/i })).toHaveAttribute('href', 'https://events.example.org/gathering');
    expect(screen.getByRole('link', { name: /booking/i })).toHaveAttribute('href', 'https://events.example.org/book');
  });
});
