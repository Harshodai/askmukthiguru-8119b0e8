import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mocks for hooks
const mockUseKpis = vi.fn();
const mockUseTimeseries = vi.fn();
const mockUseQueries = vi.fn();
const mockUseRetrievalHealth = vi.fn();
const mockUseTopFailures = vi.fn();
const mockUseOperationsSnapshot = vi.fn();
const mockUsePromptVersions = vi.fn();
const mockUseModels = vi.fn();
const mockUseQuality = vi.fn();
const mockUseSafetyEvents = vi.fn();
const mockUseAnnotations = vi.fn();
const mockUseEmptyRetrievals = vi.fn();
const mockUseDeadDocs = vi.fn();
const mockUseSimilarityTrend = vi.fn();
const mockUseDataStores = vi.fn();
const mockUseRagFlowGraph = vi.fn();
const mockUseFeedback = vi.fn();

vi.mock('@/admin/hooks/useAdminData', () => ({
  useKpis: () => mockUseKpis(),
  useTimeseries: (m: string) => mockUseTimeseries(m),
  useQueries: (filters?: unknown) => mockUseQueries(filters),
  useRetrievalHealth: () => mockUseRetrievalHealth(),
  useTopFailures: () => mockUseTopFailures(),
  useOperationsSnapshot: () => mockUseOperationsSnapshot(),
  usePromptVersions: () => mockUsePromptVersions(),
  useModels: () => mockUseModels(),
  useQuality: () => mockUseQuality(),
  useSafetyEvents: () => mockUseSafetyEvents(),
  useAnnotations: () => mockUseAnnotations(),
  useEmptyRetrievals: () => mockUseEmptyRetrievals(),
  useDeadDocs: () => mockUseDeadDocs(),
  useSimilarityTrend: () => mockUseSimilarityTrend(),
  useDataStores: () => mockUseDataStores(),
  useRagFlowGraph: (s: string) => mockUseRagFlowGraph(s),
  useFeedback: (limit?: number) => mockUseFeedback(limit),
}));

// Mock child components that rely on heavy canvas / charts / SVG
vi.mock('@/admin/components/TimeseriesChart', () => ({
  TimeseriesChart: () => <div data-testid="timeseries-chart" />,
}));
vi.mock('@/admin/components/RagasHeatmap', () => ({
  RagasHeatmap: () => <div data-testid="ragas-heatmap" />,
}));
vi.mock('@/admin/components/AskDataPanel', () => ({
  AskDataPanel: () => <div data-testid="ask-data-panel" />,
}));
vi.mock('@/admin/components/LiveFeed', () => ({
  LiveFeed: () => <div data-testid="live-feed" />,
}));
vi.mock('@/admin/components/SeedDemoButton', () => ({
  SeedDemoButton: () => <button>Seed</button>,
}));
vi.mock('@/admin/components/TraceDrawer', () => ({
  TraceDrawer: () => null,
}));
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="react-flow">{children}</div>,
  MiniMap: () => <div data-testid="minimap" />,
  Controls: () => <div data-testid="controls" />,
  Background: () => <div data-testid="background" />,
  useNodesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
  Position: { Right: 'right', Left: 'left' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
}));

import OverviewPage from '@/admin/pages/OverviewPage';
import QueriesPage from '@/admin/pages/QueriesPage';
import QualityPage from '@/admin/pages/QualityPage';
import RetrievalPage from '@/admin/pages/RetrievalPage';
import DataSourcesPage from '@/admin/pages/DataSourcesPage';
import RAGFlowPage from '@/admin/pages/RAGFlowPage';
import FeedbackPage from '@/admin/pages/FeedbackPage';

describe('Admin UX & Resiliency Hardening', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('1. OverviewPage', () => {
    it('renders without crashing when all data is null or undefined', () => {
      mockUseKpis.mockReturnValue({ data: undefined, isLoading: false });
      mockUseTimeseries.mockReturnValue({ data: undefined });
      mockUseQueries.mockReturnValue({ data: undefined });
      mockUseRetrievalHealth.mockReturnValue({ data: undefined });
      mockUseTopFailures.mockReturnValue({ data: undefined });
      mockUseOperationsSnapshot.mockReturnValue({ data: undefined });

      render(
        <MemoryRouter>
          <OverviewPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Launch readiness')).toBeInTheDocument();
      expect(screen.getByText('No recent queries found')).toBeInTheDocument();
    });

    it('renders queries with missing model and undefined fields safely', () => {
      mockUseKpis.mockReturnValue({ data: { total_queries: 5 } });
      mockUseTimeseries.mockReturnValue({ data: [] });
      mockUseQueries.mockReturnValue({
        data: [
          {
            id: 'q-1',
            status: 'ok',
            query_text: 'Test question',
            model: undefined, // model undefined test
            created_at: '2026-08-16T00:00:00Z',
            latency_ms: undefined,
          },
        ],
      });
      mockUseRetrievalHealth.mockReturnValue({ data: { sources: null } });
      mockUseTopFailures.mockReturnValue({ data: [] });
      mockUseOperationsSnapshot.mockReturnValue({ data: null });

      render(
        <MemoryRouter>
          <OverviewPage />
        </MemoryRouter>
      );

      expect(screen.getByText(/unknown/i)).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    });
  });

  describe('2. QueriesPage', () => {
    it('renders without crashing when query data and filters are empty/null', () => {
      mockUsePromptVersions.mockReturnValue({ data: undefined });
      mockUseModels.mockReturnValue({ data: undefined });
      mockUseQueries.mockReturnValue({ data: undefined, isLoading: false, isError: false });

      render(
        <MemoryRouter>
          <QueriesPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Queries')).toBeInTheDocument();
      expect(screen.getByText('No queries match your filters')).toBeInTheDocument();
    });

    it('renders queries with missing status, query_text, spans, and undefined model safely', () => {
      mockUsePromptVersions.mockReturnValue({ data: [{ id: 'p-1', name: 'Standard', version: 1 }] });
      mockUseModels.mockReturnValue({ data: [{ id: 'm-1', name: 'Claude', provider: 'Anthropic' }] });
      mockUseQueries.mockReturnValue({
        data: [
          {
            id: 'q-1',
            created_at: '2026-08-16T00:00:00Z',
            query_text: undefined,
            model: null,
            prompt_version_id: 'p-1',
            latency_ms: 150,
            status: 'ok',
            spans: [{ id: 's-1', name: 'embed', duration_ms: 50 }],
          },
          {
            id: 'q-2',
            created_at: null,
            query_text: 'Another query',
            model: 'openai/gpt-4o',
            status: 'error',
            spans: undefined,
          },
        ],
        isLoading: false,
        isError: false,
      });

      render(
        <MemoryRouter>
          <QueriesPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Standard v1')).toBeInTheDocument();
      expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    });

    it('renders error retry state when queries fail to load', () => {
      const refetch = vi.fn();
      mockUsePromptVersions.mockReturnValue({ data: [] });
      mockUseModels.mockReturnValue({ data: [] });
      mockUseQueries.mockReturnValue({ data: null, isLoading: false, isError: true, refetch });

      render(
        <MemoryRouter>
          <QueriesPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Failed to load queries from backend')).toBeInTheDocument();
    });
  });

  describe('3. QualityPage', () => {
    it('renders without crashing when quality, safety, and annotations are null or missing arrays', () => {
      mockUseQuality.mockReturnValue({ data: null, isLoading: false });
      mockUseSafetyEvents.mockReturnValue({ data: null, isLoading: false });
      mockUseAnnotations.mockReturnValue({ data: null, isLoading: false });

      render(
        <MemoryRouter>
          <QualityPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Quality')).toBeInTheDocument();
      expect(screen.getByText('No disagreements in this window')).toBeInTheDocument();
    });

    it('renders disagreement and low-confidence items with missing properties safely', () => {
      mockUseQuality.mockReturnValue({
        data: {
          disagreements: [
            {
              id: 'd-1',
              kind: 'judge_good_user_bad',
              faithfulness: 0.8,
              response_text: null,
            },
          ],
          low_confidence: [
            {
              id: 'lc-1',
              confidence: 0.4,
              response_text: 'Test low conf',
              created_at: '2026-08-16T00:00:00Z',
            },
          ],
        },
        isLoading: false,
      });
      mockUseSafetyEvents.mockReturnValue({ data: [] });
      mockUseAnnotations.mockReturnValue({ data: [] });

      render(
        <MemoryRouter>
          <QualityPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Faithfulness 80.0%')).toBeInTheDocument();
    });
  });

  describe('4. RetrievalPage', () => {
    it('renders backend unavailable card when error occurs', () => {
      mockUseRetrievalHealth.mockReturnValue({ data: null, error: new Error('Network error'), isLoading: false });
      mockUseEmptyRetrievals.mockReturnValue({ data: [] });
      mockUseDeadDocs.mockReturnValue({ data: [] });
      mockUseSimilarityTrend.mockReturnValue({ data: [] });

      render(
        <MemoryRouter>
          <RetrievalPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Backend unavailable')).toBeInTheDocument();
    });

    it('renders normally with empty source, empty retrieval, and dead docs lists', () => {
      mockUseRetrievalHealth.mockReturnValue({
        data: { total_retrievals: 10, hit_rate: 0.9, empty_retrievals: 1, avg_top_score: 0.85, sources: [] },
        error: null,
        isLoading: false,
      });
      mockUseEmptyRetrievals.mockReturnValue({ data: [] });
      mockUseDeadDocs.mockReturnValue({ data: [] });
      mockUseSimilarityTrend.mockReturnValue({ data: [{ bucket: '2026-08-16T00:00:00Z', avg_top_score: 0.8 }] });

      render(
        <MemoryRouter>
          <RetrievalPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Retrieval health')).toBeInTheDocument();
      expect(screen.getByText('0.850')).toBeInTheDocument();
    });
  });

  describe('5. DataSourcesPage', () => {
    it('renders loading skeleton and error states gracefully', () => {
      mockUseDataStores.mockReturnValue({ data: null, isLoading: true, error: null });

      const { container } = render(
        <MemoryRouter>
          <DataSourcesPage />
        </MemoryRouter>
      );
      expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
    });

    it('renders with partial or errored database stats safely', () => {
      mockUseDataStores.mockReturnValue({
        data: {
          qdrant: {
            spiritual_wisdom: { points: 89000, indexed_vectors: 89000, status: 'green', vector_size: 1024 },
          },
          neo4j: {
            nodes_by_label: { Concept: 500, Teacher: 10 },
            total_nodes: 510,
            relationships_by_type: { TEACHES: 120 },
            total_relationships: 120,
          },
          lightrag: {
            initialized: true,
            chunk_token_size: 1200,
            cache_size: 45,
            embedding_dim: 1024,
          },
        },
        isLoading: false,
        error: null,
      });

      render(
        <MemoryRouter>
          <DataSourcesPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Data Sources')).toBeInTheDocument();
      expect(screen.getByText('spiritual_wisdom')).toBeInTheDocument();
      expect(screen.getByText('Concept')).toBeInTheDocument();
      expect(screen.getByText('TEACHES')).toBeInTheDocument();
    });
  });

  describe('6. RAGFlowPage', () => {
    it('renders without crashing when graph data is null or loading', () => {
      mockUseRagFlowGraph.mockReturnValue({ data: null, isLoading: true, error: null });

      render(
        <MemoryRouter>
          <RAGFlowPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Interactive RAG Flow Graph')).toBeInTheDocument();
      expect(screen.getByText(/Loading strategy graph structure/i)).toBeInTheDocument();
    });

    it('renders error state with retry when graph fails to fetch', () => {
      mockUseRagFlowGraph.mockReturnValue({ data: null, isLoading: false, error: new Error('Failed') });

      render(
        <MemoryRouter>
          <RAGFlowPage />
        </MemoryRouter>
      );

      expect(screen.getByText('Failed to load RAG flow graph')).toBeInTheDocument();
    });
  });

  describe('7. FeedbackPage', () => {
    it('renders without crashing when the feedback API returns empty or corrupt data', () => {
      mockUseFeedback.mockReturnValue({ data: [], isLoading: false });

      render(
        <MemoryRouter>
          <FeedbackPage />
        </MemoryRouter>
      );

      expect(screen.getByText('User Feedback')).toBeInTheDocument();
      expect(screen.getByText('No feedback entries yet. Users can rate guru responses in the chat.')).toBeInTheDocument();
    });

    it('renders entries with missing tags, string timestamps, and undefined comments', () => {
      mockUseFeedback.mockReturnValue({
        data: [
          {
            id: 'msg-1234567890',
            rating: 1,
            feedback_text: undefined,
            comment: undefined,
            created_at: '2026-08-16T10:00:00Z',
          },
        ],
        isLoading: false,
      });

      render(
        <MemoryRouter>
          <FeedbackPage />
        </MemoryRouter>
      );

      expect(screen.getByText('msg-123456…')).toBeInTheDocument();
      expect(screen.getByText('Total Feedback')).toBeInTheDocument();
    });
  });
});
