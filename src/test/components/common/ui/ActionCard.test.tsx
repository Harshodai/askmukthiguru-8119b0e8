import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ActionCard } from '@/components/common/ui/ActionCard';

describe('ActionCard', () => {
  it('renders a router Link when "to" is provided', () => {
    render(
      <MemoryRouter>
        <ActionCard
          to="/practices/breath"
          icon={<span data-testid="icon">*</span>}
          title="Breath Practice"
          eyebrow={<span>Continue</span>}
          subtitle={<span>5 min</span>}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole('link', { name: /Breath Practice/i });
    expect(link).toHaveAttribute('href', '/practices/breath');
    expect(screen.getByText('Continue')).toBeInTheDocument();
    expect(screen.getByText('5 min')).toBeInTheDocument();
  });

  it('renders an anchor when "href" is provided', () => {
    render(
      <ActionCard
        href="https://example.com"
        icon={<span>→</span>}
        title="External"
      />,
    );
    expect(screen.getByRole('link')).toHaveAttribute('href', 'https://example.com');
  });
});
