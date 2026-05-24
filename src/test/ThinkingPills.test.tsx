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

  it('returns "Processing" for unknown statuses (no dot stripping)', () => {
    expect(mapStatusToLabel('Loading context...')).toBe('Processing');
    expect(mapStatusToLabel('Custom step...')).toBe('Processing');
    expect(mapStatusToLabel('Done')).toBe('Processing');
    expect(mapStatusToLabel('Complete')).toBe('Processing');
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
    // Vertical stepper shows label text in multiple places; getAllByText avoids ambiguity
    expect(screen.getAllByText('Composing').length).toBeGreaterThan(0);
  });
});
