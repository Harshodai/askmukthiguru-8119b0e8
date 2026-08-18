import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EuAiBadge } from '@/components/compliance/EuAiBadge';

describe('EuAiBadge Component', () => {
  it('renders default AI Generated badge with proper accessibility attributes', () => {
    render(<EuAiBadge />);

    const badge = screen.getByTestId('eu-ai-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('AI Generated');
    expect(badge).toHaveAttribute(
      'aria-label',
      'AI Generated content - EU AI Act Article 50 Disclosure'
    );
    expect(badge.tagName).toBe('SPAN');
    expect(badge).toHaveAttribute('role', 'status');
  });

  it('renders AI Assisted variant correctly', () => {
    render(<EuAiBadge originType="ai_assisted" />);

    const badge = screen.getByTestId('eu-ai-badge');
    expect(badge).toHaveTextContent('AI Assisted');
    expect(badge).toHaveAttribute(
      'aria-label',
      'AI Assisted content - EU AI Act Article 50 Disclosure'
    );
  });

  it('renders Human Authored variant correctly', () => {
    render(<EuAiBadge originType="human_generated" />);

    const badge = screen.getByTestId('eu-ai-badge');
    expect(badge).toHaveTextContent('Human Authored');
    expect(badge).toHaveAttribute(
      'aria-label',
      'Human Authored content - EU AI Act Article 50 Disclosure'
    );
  });

  it('renders as a clickable button and responds to click event when onClick is provided', () => {
    const handleClick = vi.fn();
    render(<EuAiBadge onClick={handleClick} />);

    const badge = screen.getByTestId('eu-ai-badge');
    expect(badge.tagName).toBe('BUTTON');
    expect(badge).toHaveAttribute('type', 'button');

    fireEvent.click(badge);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('hides visible label when showLabel is false but retains accessible label', () => {
    render(<EuAiBadge showLabel={false} />);

    const badge = screen.getByTestId('eu-ai-badge');
    expect(badge).toHaveAttribute(
      'aria-label',
      'AI Generated content - EU AI Act Article 50 Disclosure'
    );
  });

  it('applies custom size and classNames properly', () => {
    render(<EuAiBadge size="md" className="custom-test-class" />);

    const badge = screen.getByTestId('eu-ai-badge');
    expect(badge).toHaveClass('custom-test-class');
    expect(badge).toHaveClass('text-xs');
  });
});
