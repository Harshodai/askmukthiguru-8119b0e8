import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, act, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n';
import { KGConceptMap } from '@/components/kg/KGConceptMap';
import { getAccessToken } from '@/lib/chat/auth';

vi.mock('@/lib/chat/config', () => ({ getAIConfig: () => ({ endpoint: 'http://localhost:8000/api/chat' }) }));
vi.mock('@/lib/chat/auth', () => ({ getAccessToken: vi.fn(() => Promise.resolve('token')) }));

vi.mock('@xyflow/react', async () => {
  const React = await import('react');
  return {
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    MiniMap: () => null,
    Position: { Top: 'top', Right: 'right', Bottom: 'bottom', Left: 'left' },
    ReactFlow: ({
      nodes,
      edges,
      onNodeClick,
      children,
    }: {
      nodes: Array<{ id: string; data: { label: string } }>;
      edges?: Array<{ id: string; sourceHandle?: string; targetHandle?: string }>;
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
        {edges?.map((edge) => (
          <div key={edge.id} data-testid="kg-edge" data-source-handle={edge.sourceHandle ?? ''} data-target-handle={edge.targetHandle ?? ''} />
        ))}
        {children}
      </div>
    ),
  };
});


const renderWithI18n = (ui: React.ReactElement) => render(<MemoryRouter><I18nextProvider i18n={i18n}>{ui}</I18nextProvider></MemoryRouter>);

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

  it('links a memory node to its original conversation and says "Source unavailable" when unproven', async () => {
    const convId = '3f2b8c1e-9a4d-4e6f-8a1b-2c3d4e5f6a7b';
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              nodes: [
                { id: 'memory:m1', label: 'Linked memory', type: 'Memory', source_ref: { kind: 'conversation', id: convId } },
                { id: 'memory:m2', label: 'Legacy memory', type: 'Memory', source_ref: null },
                { id: 'concept:c1', label: 'Stillness', type: 'Concept' },
              ],
              edges: [],
            }),
        }),
      ),
    );

    renderWithI18n(<KGConceptMap />);
    await waitFor(() => expect(screen.getByLabelText('Linked memory')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Linked memory'));
    const links = await screen.findAllByTestId('memory-source-link');
    expect(links[0].getAttribute('href')).toContain(`/chat?conversation=${convId}`);
    expect(screen.queryByTestId('memory-source-unavailable')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Legacy memory'));
    expect((await screen.findAllByTestId('memory-source-unavailable')).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('memory-source-link')).not.toBeInTheDocument();

    // Public ontology concepts have no user-owned source, so no source row at all.
    fireEvent.click(screen.getByLabelText('Stillness'));
    expect(screen.queryByTestId('memory-source-link')).not.toBeInTheDocument();
    expect(screen.queryByTestId('memory-source-unavailable')).not.toBeInTheDocument();
  });

  it('passes the focused search query to the personal endpoint', async () => {
    const fetchMock = vi.fn((..._args: any[]) =>
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

  it('shows a personal empty state without error banner or demo nodes when personal subgraph is empty', async () => {
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
        screen.getByText(/your personal wisdom map is blooming/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByTestId('kg-node')).not.toBeInTheDocument();
    expect(screen.queryByText('Beautiful State')).not.toBeInTheDocument();
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

  it('shows sign-in CTA on 401/403 auth error instead of the generic unavailable dead-end', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 403 })));

    renderWithI18n(<KGConceptMap />);
    await waitFor(() =>
      expect(screen.getByText(/sign in to view/i)).toBeInTheDocument(),
    );
    const cta = screen.getByRole('link', { name: /sign in/i });
    expect(cta.getAttribute('href')).toBe('/auth');
    expect(screen.queryByText(/unavailable right now/i)).not.toBeInTheDocument();
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

  it('attaches graph edges to directional handles instead of defaulting to top/bottom', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              nodes: [
                { id: 'a', label: 'A', type: 'Memory' },
                { id: 'b', label: 'B', type: 'Concept' },
              ],
              edges: [{ id: 'a-b', source: 'a', target: 'b', type: 'RELATES_TO' }],
            }),
        }),
      ),
    );

    renderWithI18n(<KGConceptMap />);
    await waitFor(() => expect(screen.getByTestId('kg-edge')).toBeInTheDocument());
    const edge = screen.getByTestId('kg-edge');
    expect(edge.getAttribute('data-source-handle')).toMatch(/^source-/);
    expect(edge.getAttribute('data-target-handle')).toMatch(/^target-/);
  });

  it('shows node details immediately inside the graph after a node click', async () => {
    const testData = {
      nodes: [
        { id: '1', label: 'Beautiful State', type: 'State', teacher: 'Sri Preethaji' },
        { id: '2', label: 'Witnessing Awareness', type: 'Practice', teacher: 'Sri Preethaji' },
        { id: '3', label: 'Compassion', type: 'Practice', teacher: 'Sri Preethaji' },
      ],
      edges: [
        { source: '1', target: '2', label: 'cultivates' },
        { source: '1', target: '3', label: 'leads to' },
      ],
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(testData),
        }),
      ),
    );

    renderWithI18n(<KGConceptMap />);
    const node = await screen.findByRole('button', { name: 'Beautiful State' });
    fireEvent.click(node);

    const details = screen.getByRole('region', { name: /beautiful state details/i });
    expect(details).toBeInTheDocument();
    expect(within(details).getByText(/2 connections/i)).toBeInTheDocument();
  });

  it('shows error banner and injects no demo nodes when general subgraph fails', async () => {
    vi.mocked(getAccessToken).mockResolvedValueOnce(undefined);

    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })));

    renderWithI18n(<KGConceptMap />);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load/i);
    expect(screen.queryByTestId('kg-node')).not.toBeInTheDocument();
    expect(screen.queryByText('Beautiful State')).not.toBeInTheDocument();
    expect(screen.queryByText(/example map/i)).not.toBeInTheDocument();
  });

  it('shows no teachings error and injects no demo nodes when general subgraph is empty', async () => {
    vi.mocked(getAccessToken).mockResolvedValueOnce(undefined);

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
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/(no teachings found|no concepts found)/i);
    expect(screen.queryByTestId('kg-node')).not.toBeInTheDocument();
    expect(screen.queryByText('Beautiful State')).not.toBeInTheDocument();
    expect(screen.queryByText(/example map/i)).not.toBeInTheDocument();
  });

  it('categorizes spiritual nodes with distinct visual styles and badges', async () => {
    const { getNodeVisual } = await import('@/components/kg/KGConceptMap');
    expect(getNodeVisual('user').badge).toBe('Seeker (You)');
    expect(getNodeVisual('inquiry').badge).toBe('Sacred Inquiry');
    expect(getNodeVisual('notebookitem').badge).toBe('Sacred Inquiry');
    expect(getNodeVisual('practice').badge).toBe('Sacred Practice');
    expect(getNodeVisual('teacher').badge).toBe('Master Teacher');
    expect(getNodeVisual('state', 'Beautiful State', 'Calm').badge).toBe('Beautiful State');
    expect(getNodeVisual('state', 'Suffering State', 'Anxiety').badge).toBe('Suffering State');
    expect(getNodeVisual('concept', null, 'Witnessing Awareness').badge).toBe('Sacred Practice');
    expect(getNodeVisual('concept', null, 'Sri Krishnaji').badge).toBe('Master Teacher');
  });

  it('shows rich reflection excerpt, associated practice, and chat exploration in node details', async () => {
    const mockData = {
      nodes: [
        {
          id: 'state:anxiety',
          label: 'Anxiety',
          type: 'State',
          state_category: 'Suffering State',
          content_preview: 'I feel overwhelmed with work deadlines.',
        },
      ],
      edges: [],
    };
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(mockData) })));

    renderWithI18n(<KGConceptMap />);
    const node = await screen.findByRole('button', { name: 'Anxiety' });
    fireEvent.click(node);

    // Context / excerpt rendered in details panel
    expect(screen.getAllByText(/I feel overwhelmed with work deadlines/i).length).toBeGreaterThan(0);
    // Explore in chat button
    expect(screen.getAllByRole('button', { name: /explore in chat/i }).length).toBeGreaterThan(0);
    // Associated practice
    expect(screen.getAllByRole('link', { name: /practice/i }).length).toBeGreaterThan(0);
  });

  describe('Personal Knowledge Graph Scope Isolation & Consent Governance', () => {
    it('only calls /api/kg/personal-subgraph when scope="personal"', async () => {
      const fetchMock = vi.fn((..._args: any[]) =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ nodes: [], edges: [] }),
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      renderWithI18n(<KGConceptMap scope="personal" hasConsent={true} />);
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? '');
      expect(calledUrl).toContain('/api/kg/personal-subgraph');
      expect(calledUrl).not.toContain('/api/kg/subgraph?');
    });

    it('renders paused card when scope="personal" and hasConsent !== true, invoking onApproveConsent when clicked', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() =>
          Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ nodes: [], edges: [] }),
          }),
        ),
      );

      const onApprove = vi.fn();
      renderWithI18n(
        <KGConceptMap scope="personal" hasConsent={false} onApproveConsent={onApprove} />,
      );

      await waitFor(() => {
        expect(screen.getByText(/personal wisdom map paused/i)).toBeInTheDocument();
      });
      expect(
        screen.getByText(
          /allow mukthi guru to remember your reflections to weave your personal spiritual journey/i,
        ),
      ).toBeInTheDocument();

      const approveBtn = screen.getByRole('button', {
        name: /approve & enable personal wisdom map/i,
      });
      expect(approveBtn).toBeInTheDocument();
      fireEvent.click(approveBtn);
      expect(onApprove).toHaveBeenCalledTimes(1);
    });

    it('renders blooming state with 0 reflections message and inquiry buttons when scope="personal" and hasConsent === true', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() =>
          Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ nodes: [], edges: [] }),
          }),
        ),
      );

      renderWithI18n(<KGConceptMap scope="personal" hasConsent={true} />);

      await waitFor(() => {
        expect(
          screen.getByText(/your personal wisdom map is blooming/i),
        ).toBeInTheDocument();
      });
      expect(
        screen.getByText(/0 reflections recorded yet. ask a question or share a reflection to begin/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', {
          name: /how do i shift from a suffering state to a beautiful state/i,
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', {
          name: /teach me the serene mind practice/i,
        }),
      ).toBeInTheDocument();
    });

    it('calls general /api/kg/subgraph when scope="general"', async () => {
      const fetchMock = vi.fn((..._args: any[]) =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              nodes: [{ id: 'c1', label: 'Ekam Concept', type: 'Concept' }],
              edges: [],
            }),
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      renderWithI18n(<KGConceptMap scope="general" />);
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? '');
      expect(calledUrl).toContain('/api/kg/subgraph?');
      expect(calledUrl).not.toContain('/api/kg/personal-subgraph');
    });
  });
});
