import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import {
  DemoModal,
  getTourOutcome,
  hasSeenTour,
  recordTourOutcome,
  WelcomePrompt,
} from '@/components/landing/DemoModal';

beforeEach(() => {
  localStorage.clear();
});

describe('landing tour persistence', () => {
  it('does not persist merely because the tour opens', () => {
    render(
      <MemoryRouter>
        <DemoModal isOpen onComplete={vi.fn()} onDismiss={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(getTourOutcome()).toBeNull();
    expect(hasSeenTour()).toBe(false);
  });

  it('persists only an explicit onboarding outcome', () => {
    recordTourOutcome('dismissed');
    expect(getTourOutcome()).toBe('dismissed');
    expect(hasSeenTour()).toBe(true);
  });
});

describe('landing tour controls', () => {
  it('provides labelled skip, back, next, and close controls', () => {
    render(
      <MemoryRouter>
        <DemoModal isOpen onComplete={vi.fn()} onDismiss={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: 'Close tour' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Skip tour' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back to previous tour step' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next tour step' })).toBeInTheDocument();
  });

  it('dismisses with Escape and completes from a path link', () => {
    const onDismiss = vi.fn();
    const onComplete = vi.fn();
    const { rerender } = render(
      <MemoryRouter>
        <DemoModal isOpen onComplete={onComplete} onDismiss={onDismiss} />
      </MemoryRouter>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onDismiss).toHaveBeenCalledTimes(1);

    rerender(
      <MemoryRouter>
        <DemoModal isOpen onComplete={onComplete} onDismiss={onDismiss} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('link', { name: 'Talk now' }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });
});

describe('first-visit welcome prompt', () => {
  it('is compact, non-modal, and launches only when requested', () => {
    const onStartTour = vi.fn();
    render(<WelcomePrompt isVisible onStartTour={onStartTour} onDismiss={vi.fn()} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /take a three-step tour/i }));
    expect(onStartTour).toHaveBeenCalledTimes(1);
  });
});
