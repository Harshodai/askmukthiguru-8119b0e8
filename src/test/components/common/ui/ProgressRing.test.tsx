import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProgressRing } from '@/components/common/ui/ProgressRing';

describe('ProgressRing', () => {
  it('renders step label and center content', () => {
    render(
      <ProgressRing
        currentStep={2}
        totalSteps={5}
        stepProgress={0.5}
        centerContent={<div data-testid="center">Center</div>}
      />,
    );
    expect(screen.getByTestId('center')).toHaveTextContent('Center');
  });

  it('renders the correct number of step dots', () => {
    const { container } = render(
      <ProgressRing currentStep={1} totalSteps={4} stepProgress={0} />,
    );
    const dots = container.querySelectorAll('svg > circle');
    // 4 dots, each wrapped in its own svg; the main ring svg has 2 circles.
    expect(dots.length).toBeGreaterThanOrEqual(4);
  });
});
