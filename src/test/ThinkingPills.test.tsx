import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThinkingPills, mapStatusToLabel, type PipelineStep } from '@/components/chat/ThinkingPills';

describe('mapStatusToLabel', () => {
  it('maps known backend statuses to short labels', () => {
    expect(mapStatusToLabel('Checking message safety...')).toBe('Safety check');
    expect(mapStatusToLabel('Understanding your question...')).toBe('Understanding');
    expect(mapStatusToLabel('Searching knowledge base...')).toBe('Searching wisdom');
    expect(mapStatusToLabel('Composing response...')).toBe('Composing');
    expect(mapStatusToLabel('Generating answer...')).toBe('Generating');
    expect(mapStatusToLabel('Verifying answer...')).toBe('Verifying');
  });

  it('strips trailing ellipsis from unknown statuses', () => {
    expect(mapStatusToLabel('Loading context...')).toBe('Loading context');
    expect(mapStatusToLabel('Custom step...')).toBe('Custom step');
  });

  it('returns raw string when no trailing ellipsis', () => {
    expect(mapStatusToLabel('Done')).toBe('Done');
  });
});

describe('ThinkingPills', () => {
  it('renders nothing when visible is false', () => {
    const steps: PipelineStep[] = [
      { id: 'step-0', label: 'Safety check', status: 'active' },
    ];
    const { container } = render(<ThinkingPills steps={steps} visible={false} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when steps is empty', () => {
    const { container } = render(<ThinkingPills steps={[]} visible={true} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders pills with correct labels', () => {
    const steps: PipelineStep[] = [
      { id: 'step-0', label: 'Safety check', status: 'done' },
      { id: 'step-1', label: 'Searching wisdom', status: 'active' },
      { id: 'step-2', label: 'Composing', status: 'pending' },
    ];
    render(<ThinkingPills steps={steps} visible={true} />);
    expect(screen.getByText('Safety check')).toBeInTheDocument();
    expect(screen.getByText('Searching wisdom')).toBeInTheDocument();
    expect(screen.getByText('Composing')).toBeInTheDocument();
  });
});
