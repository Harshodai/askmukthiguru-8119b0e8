import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

// ResizeObserver mock
globalThis.ResizeObserver = class ResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
};

// Mocks
vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
    from: vi.fn(() => ({
      select: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockReturnThis(),
      maybeSingle: vi.fn().mockResolvedValue({ data: null, error: null }),
      delete: vi.fn().mockReturnThis(),
      eq: vi.fn().mockResolvedValue({ error: null }),
    })),
    storage: {
      from: vi.fn(() => ({
        upload: vi.fn().mockResolvedValue({ error: null }),
        getPublicUrl: vi.fn().mockReturnValue({ data: { publicUrl: 'https://example.com/img.jpg' } }),
      })),
    },
  },
}));

vi.mock('@/admin/lib/api', () => ({
  getWisdomTips: vi.fn().mockResolvedValue({ tips: [], expires_at: new Date().toISOString(), generated_at: new Date().toISOString() }),
  regenerateWisdomTips: vi.fn().mockResolvedValue({ tips: [], expires_at: new Date().toISOString(), generated_at: new Date().toISOString() }),
  getCacheMetrics: vi.fn().mockResolvedValue({ tiers: { hot: { available: true }, exact: { available: true }, semantic: { available: true } } }),
  clearCache: vi.fn().mockResolvedValue({ tiers: { hot: 'cleared', exact: 'cleared', semantic: 'cleared' } }),
  listStagingQueue: vi.fn().mockResolvedValue([]),
  reviewStagingItem: vi.fn().mockResolvedValue({ message: 'Success' }),
  listLogs: vi.fn().mockResolvedValue([]),
  runEval: vi.fn().mockResolvedValue({ summary: { passed: 5, total: 5 } }),
  deleteGoldenQuestion: vi.fn().mockResolvedValue({ success: true }),
  triggerReingest: vi.fn().mockResolvedValue({ success: true }),
  submitIngestion: vi.fn().mockResolvedValue({ message: 'Started' }),
  getIngestionStatus: vi.fn().mockResolvedValue({}),
  uploadDocument: vi.fn().mockResolvedValue({ message: 'Uploaded' }),
  ingestBook: vi.fn().mockResolvedValue({ task_id: 'task-1' }),
  activatePromptVersion: vi.fn().mockResolvedValue({ success: true }),
}));

vi.mock('@/admin/hooks/useAdminData', () => ({
  useTriggers: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  useTriggerTrend: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  useTopics: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  usePromptVersions: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  usePromptMetrics: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  useEvalRuns: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  useGoldenQuestions: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  useIngestionRuns: vi.fn(() => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() })),
  useIngestionHealth: vi.fn(() => ({ data: { total_runs: 0, ok: 0, partial: 0, failed: 0, total_chunks: 0 }, isLoading: false, isError: false, refetch: vi.fn() })),
}));

import { AdminFiltersProvider } from '@/admin/lib/filtersStore';
import DailyTeachingPage from '@/admin/pages/DailyTeachingPage';
import TeachingTipsPage from '@/admin/pages/TeachingTipsPage';
import TriggersPage from '@/admin/pages/TriggersPage';
import TopicsPage from '@/admin/pages/TopicsPage';
import PromptsPage from '@/admin/pages/PromptsPage';
import EvalsPage from '@/admin/pages/EvalsPage';
import StagingQueuePage from '@/admin/pages/StagingQueuePage';
import IngestionPage from '@/admin/pages/IngestionPage';
import CachePage from '@/admin/pages/CachePage';
import LogsPage from '@/admin/pages/LogsPage';

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminFiltersProvider>
        <BrowserRouter>{ui}</BrowserRouter>
      </AdminFiltersProvider>
    </QueryClientProvider>
  );
}

describe('Admin 10 Pages Resiliency Test Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders DailyTeachingPage without throwing on empty/null data', async () => {
    renderWithProviders(<DailyTeachingPage />);
    expect(screen.getByText('Daily Teaching')).toBeDefined();
    expect(screen.getByText('No active teaching. Upload one below.')).toBeDefined();
  });

  it('renders TeachingTipsPage without throwing on empty/null data', async () => {
    renderWithProviders(<TeachingTipsPage />);
    expect(screen.getByText('Teaching Tips')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('Regenerate Tips')).toBeDefined();
    });
  });

  it('renders TriggersPage without throwing on empty/null data', async () => {
    renderWithProviders(<TriggersPage />);
    expect(screen.getByText('Triggers')).toBeDefined();
    expect(screen.getByText('Serene Mind highlight')).toBeDefined();
  });

  it('renders TopicsPage without throwing on empty/null data', async () => {
    renderWithProviders(<TopicsPage />);
    expect(screen.getByText('Topic clusters')).toBeDefined();
    expect(screen.getByText('No topic clusters available yet')).toBeDefined();
  });

  it('renders PromptsPage without throwing on empty/null data', async () => {
    renderWithProviders(<PromptsPage />);
    expect(screen.getByText('Prompts')).toBeDefined();
    expect(screen.getByText('Side-by-side diff')).toBeDefined();
  });

  it('renders EvalsPage without throwing on empty/null data', async () => {
    renderWithProviders(<EvalsPage />);
    expect(screen.getByText('Evals')).toBeDefined();
    expect(screen.getByText('Golden questions (0)')).toBeDefined();
  });

  it('renders StagingQueuePage without throwing on empty/null data', async () => {
    renderWithProviders(<StagingQueuePage />);
    expect(screen.getByText(/Data Quality Staging Queue/)).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText(/No items in the staging queue/)).toBeDefined();
    });
  });

  it('renders IngestionPage without throwing on empty/null data', async () => {
    renderWithProviders(<IngestionPage />);
    expect(screen.getByText('Ingestion')).toBeDefined();
    expect(screen.getByText('Submit New Content')).toBeDefined();
  });

  it('renders CachePage without throwing on empty/null data', async () => {
    renderWithProviders(<CachePage />);
    expect(screen.getByText('Cache Management')).toBeDefined();
    expect(screen.getByText('Hot Cache')).toBeDefined();
  });

  it('renders LogsPage without throwing on empty/null data', async () => {
    renderWithProviders(<LogsPage />);
    expect(screen.getByText('Logs')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('No logs found matching criteria')).toBeDefined();
    });
  });
});
