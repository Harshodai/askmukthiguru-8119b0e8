import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Suspense, type ComponentType } from 'react';
import { lazyWithRetry } from '@/lib/lazyWithRetry';

beforeEach(() => {
  sessionStorage.clear();
});

// Compile-time assertion: a component with a REQUIRED prop must be assignable
// to lazyWithRetry's generic constraint (TS2344 under strictFunctionTypes
// otherwise, e.g. `ComponentType<unknown>`). This mirrors the real usage in
// ChatMessage.tsx (LazyWisdomCardGenerator) and the React.lazy type contract.
const RequiredPropComponent = ({ title }: { title: string }) => <h1>{title}</h1>;

const LazyRequiredProp = lazyWithRetry<ComponentType<{ title: string }>>(
  async () => ({ default: RequiredPropComponent }),
);

describe('lazyWithRetry', () => {
  it('renders a lazy-loaded component with a required prop', async () => {
    render(
      <Suspense fallback={<span>loading</span>}>
        <LazyRequiredProp title="Mukthi" />
      </Suspense>,
    );
    expect(await screen.findByText('Mukthi')).toBeInTheDocument();
  });

  it('sets the reload flag once on a failed chunk import so a refresh happens', async () => {
    const Failing = lazyWithRetry(
      async () => {
        throw new Error('chunk fetch failed');
      },
    );
    render(
      <Suspense fallback={<span>loading</span>}>
        <Failing />
      </Suspense>,
    );
    // The wrapper reloads the page on first failure and never resolves in-process;
    // jsdom cannot reload, so the observable contract is the flag it sets first.
    await waitFor(() => expect(sessionStorage.getItem('chunk_reload_attempted')).toBe('1'));
  });
});
