import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/i18n';
import { KGConceptMap, DEMO_DATA } from '@/components/kg/KGConceptMap';

vi.mock('@/lib/chat/config', () => ({ getAIConfig: () => ({ endpoint: 'http://localhost:8000/api/chat' }) }));
vi.mock('@/lib/chat/auth', () => ({ getAccessToken: vi.fn(() => Promise.resolve('token')) }));

vi.mock('@xyflow/react', async () => {
  const React = await import('react');
  return {
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    MiniMap: () => null,
    Position: { Top: 'top', Bottom: 'bottom' },
    ReactFlow: ({
      nodes,
      onNodeClick,
      children,
    }: {
      nodes: Array<{ id: string; data: { label: string } }>;
      onNodeClick?: (event: unknown, node: { id: string }) => void;
      children?: React.ReactNode;
    }) => (
      <div data-testid="react-flow">
        {nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            aria-label={node.data.label}
            data-testid="kg-node"
            onClick={(event) => onNodeClick?.(event, node)}
          >
            {node.data.label}
          </button>
        ))}
        {children}
      </div>
    ),
  };
});

const liveData = { nodes: [{ id: 'n1', label: 'Beautiful State', type: 'State', teacher: 'Sri Preethaji' }], edges: [] };

const renderWithI18n = (ui: React.ReactElement) => render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);

const advanceSimulation = async () => {
  // Let the KG force-directed simulation run through its frames.
  // Flush any pending state updates from the simulation init, then advance
  // enough fake-RAF frames for the throttled setSimHeat to fire.
  await act(async () => {
    await Promise.resolve();
    for (let i = 0; i < 40; i++) {
      await vi.advanceTimersByTimeAsync(16);
    }
    await Promise.resolve();
  });
};

describe('KGConceptMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders live personal subgraph without demo data', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            nodes: [
              {
                id: 'memory:m1',
                label: 'Stillness',
                type: 'Memory',
                state_category: 'Beautiful State',
                content_preview: 'A reflection about stillness.',
              },
            ],
            edges: [],
          }),
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    renderWithI18n(<KGConceptMap />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByLabelText('Stillness')).toBeInTheDocument());
    expect(screen.queryByText(/example map/i)).not.toBeInTheDocument();
  });

  it('passes the focused search query to the personal endpoint', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            nodes: [{ id: 'n1', label: 'Meditation', type: 'Practice' }],
            edges: [],
          }),
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    renderWithI18n(<KGConceptMap />);
    const input = screen.getByRole('textbox', { name: /knowledge graph query/i });
    fireEvent.change(input, { target: { value: 'meditation' } });
    fireEvent.click(screen.getByRole('button', { name: /explore/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toContain('query=meditation');
  });

  it('shows a personal empty state instead of synthetic example data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ nodes: [], edges: [] }),
        }),
      ),
    );

    renderWithI18n(<KGConceptMap />);
    await waitFor(() =>
      expect(
        screen.getByText(/your personal wisdom map is empty/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/example map/i)).not.toBeInTheDocument();
  });

  it('shows personal-map error on authenticated fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })));

    renderWithI18n(<KGConceptMap />);
    await waitFor(() =>
      expect(
        screen.getByText(/personal wisdom map is unavailable/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/retry live map/i)).not.toBeInTheDocument();
  });

  it('does not render an unrecognized teacher placeholder', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              nodes: [{ id: 'n1', label: 'Beautiful State', type: 'Concept', teacher: 'base' }],
              edges: [],
            }),
        }),
      ),
    );

    renderWithI18n(<KGConceptMap />);
    await waitFor(() => expect(screen.getByLabelText('Beautiful State')).toBeInTheDocument());
    expect(screen.queryByText('base')).not.toBeInTheDocument();
  });

  it('keeps the curated demo graph limited to on-brand teachers', () => {
    const names = DEMO_DATA.nodes.map((n) => n.label.toLowerCase());
    const teachers = DEMO_DATA.nodes.map((n) => (n.teacher || '').toLowerCase());
    const hasOffBrand = [...names, ...teachers].some((s) => s.includes('krishnamurti'));
    expect(hasOffBrand).toBe(false);
    expect(DEMO_DATA.nodes.some((n) => n.label === 'Sri Krishnaji')).toBe(true);
  });
});;
