import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SereneMindProvider, useSereneMind } from '@/components/common/SereneMindProvider';

// Mock framer-motion to avoid animation timer noise in tests
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

const Probe = () => {
  const { isOpen, open, close } = useSereneMind();
  return (
    <div>
      <span data-testid="state">{isOpen ? 'open' : 'closed'}</span>
      <button onClick={() => open()}>OpenBreath</button>
      <button onClick={() => open('audio')}>OpenAudio</button>
      <button onClick={() => close()}>Close</button>
    </div>
  );
};

describe('SereneMindProvider', () => {
  it('throws if useSereneMind is used outside provider', () => {
    const Bad = () => {
      useSereneMind();
      return null;
    };
    // Suppress error logging for this expected throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Bad />)).toThrow(/SereneMindProvider/);
    spy.mockRestore();
  });

  it('opens and closes via context', () => {
    render(
      <SereneMindProvider>
        <Probe />
      </SereneMindProvider>
    );
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
    act(() => {
      fireEvent.click(screen.getByText('OpenBreath'));
    });
    expect(screen.getByTestId('state')).toHaveTextContent('open');
    act(() => {
      fireEvent.click(screen.getByText('Close'));
    });
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('accepts an initial tab argument', () => {
    render(
      <SereneMindProvider>
        <Probe />
      </SereneMindProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText('OpenAudio'));
    });
    // Modal should render an Audio tab, marked as selected
    const audioTab = screen.getByRole('tab', { name: /Audio/i });
    expect(audioTab).toHaveAttribute('aria-selected', 'true');
  });
});
