import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  ThinkingPills,
  mapStatusToLabel,
  mapNodeToLabel,
  type PipelineStep,
} from '@/components/chat/ThinkingPills';

describe('mapStatusToLabel', () => {
  it('maps known backend statuses to descriptive labels', () => {
    expect(mapStatusToLabel('Checking message safety...')).toBe('Safety check');
    expect(mapStatusToLabel('Understanding your question...')).toBe('Understanding query');
    expect(mapStatusToLabel('Searching knowledge base...')).toBe('Searching sacred wisdom');
    expect(mapStatusToLabel('Composing response...')).toBe('Composing guidance');
    expect(mapStatusToLabel('Generating answer...')).toBe('Synthesizing wisdom');
    expect(mapStatusToLabel('Verifying answer...')).toBe('Verifying sacred teachings');
  });

  it('returns "Contemplating" for unknown statuses', () => {
    expect(mapStatusToLabel('Loading context...')).toBe('Contemplating');
    expect(mapStatusToLabel('Custom step...')).toBe('Contemplating');
    expect(mapStatusToLabel('Done')).toBe('Contemplating');
    expect(mapStatusToLabel('Complete')).toBe('Contemplating');
  });
});

describe('mapNodeToLabel', () => {
  it('maps graph node names to friendly stage labels', () => {
    expect(mapNodeToLabel('input_guardrail')).toBe('Safety check');
    expect(mapNodeToLabel('intent_router')).toBe('Understanding query');
    expect(mapNodeToLabel('retrieve_documents')).toBe('Searching sacred wisdom');
    expect(mapNodeToLabel('rerank_documents')).toBe('Refining relevance');
    expect(mapNodeToLabel('grade_documents')).toBe('Filtering relevance');
    expect(mapNodeToLabel('generate_answer')).toBe('Composing guidance');
    expect(mapNodeToLabel('verify_answer')).toBe('Verifying sacred teachings');
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

  it('renders fallback label when visible with no steps', () => {
    render(<ThinkingPills steps={[]} visible={true} fallbackLabel="Analyzing…" />);
    expect(screen.getByText(/Analyzing/)).toBeInTheDocument();
  });

  it('shows the latest active step and reveals full list when expanded', () => {
    const steps: PipelineStep[] = [
      { id: 'step-0', label: 'Safety check', status: 'done' },
      { id: 'step-1', label: 'Searching sacred wisdom', status: 'active' },
      { id: 'step-2', label: 'Composing guidance', status: 'pending' },
    ];
    render(<ThinkingPills steps={steps} visible={true} />);
    expect(screen.getByText(/Searching sacred wisdom/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /toggle thinking details/i }));
    expect(screen.getByText('Safety check')).toBeInTheDocument();
    expect(screen.getByText('Composing guidance')).toBeInTheDocument();
  });

  it('tracks step / total_steps and displays honest progress with fraction and percentage', () => {
    const steps: PipelineStep[] = [
      { id: 'step-1', label: 'Safety check', status: 'done', step: 1, totalSteps: 8 },
      { id: 'step-2', label: 'Understanding query', status: 'done', step: 2, totalSteps: 8 },
      { id: 'step-3', label: 'Searching sacred wisdom', status: 'active', step: 3, totalSteps: 8 },
    ];
    render(<ThinkingPills steps={steps} visible={true} />);
    expect(screen.getByText('Step 3/8: Searching sacred wisdom (37%)')).toBeInTheDocument();
  });


  it('renders retrieved teaching evidence without exposing hidden reasoning', () => {
    render(
      <ThinkingPills
        steps={[{ id: 'step-2', label: 'Searching sacred wisdom', status: 'active' }]}
        visible={true}
        teachingPreview={[
          {
            title: 'Awareness and the Beautiful State',
            teacher: 'Sri Preethaji',
            url: 'https://example.com/teaching',
            excerpt: 'A short source-backed teaching excerpt.',
          },
        ]}
      />,
    );
    expect(screen.getByText('Teachings grounding this answer')).toBeInTheDocument();
    expect(screen.getByText('Awareness and the Beautiful State')).toBeInTheDocument();
    expect(screen.getByText('A short source-backed teaching excerpt.')).toBeInTheDocument();
  });

  it('keeps the thinking hierarchy at the same readable font size', () => {
    const steps: PipelineStep[] = [
      { id: 'step-0', label: 'Safety check', status: 'done' },
      { id: 'step-1', label: 'Searching sacred wisdom', status: 'active' },
    ];
    render(<ThinkingPills steps={steps} visible={true} />);
    const toggle = screen.getByRole('button', { name: /toggle thinking details/i });
    fireEvent.click(toggle);
    const rows = screen.getAllByText(/Safety check|Searching sacred wisdom/);
    expect(rows.length).toBeGreaterThan(0);
    rows.forEach((row) => expect(row.className).toContain('text-[15px]'));
  });

  it('prevents false 100% completion before tokens arrive (caps at 95%)', () => {
    const steps: PipelineStep[] = [
      { id: 'step-8', label: 'Verifying sacred teachings', status: 'active', step: 8, totalSteps: 8 },
    ];
    render(<ThinkingPills steps={steps} visible={true} />);
    expect(screen.getByText('Step 8/8: Verifying sacred teachings (95%)')).toBeInTheDocument();
  });
});
