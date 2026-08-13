import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/admin/hooks/useAdminData', () => ({
  useKpis: () => ({ data: { total_queries: 1, total_seekers: 1, p50_latency_ms: 100, p95_latency_ms: 200, hallucination_rate: 0, serene_mind_trigger_rate: 0, thumbs_up_rate: 1, estimated_cost_usd: 0.01, error_rate: 0 } }),
  useTimeseries: () => ({ data: [] }),
  useQueries: () => ({ data: [{ id: 'trace-1', status: 'ok', query_text: 'private seeker question', created_at: '2026-08-13T00:00:00Z', latency_ms: 100, model: 'google/gemini' }] }),
  useRetrievalHealth: () => ({ data: { sources: [] } }),
  useTopFailures: () => ({ data: [{ query_id: 'trace-1', faithfulness: 0.5, query_text: 'private failure question', reason: 'private review note', created_at: '2026-08-13T00:00:00Z' }] }),
  useOperationsSnapshot: () => ({ data: { sample_size: 1, failure_count: 0, failure_rate: 0, average_latency_ms: 100, cost_estimate_usd: 0.01, model_policy_id: 'gemini-flash-budget-v1', budget_guard_enabled: false } }),
}));
vi.mock('@/admin/components/AskDataPanel', () => ({ AskDataPanel: () => <div /> }));
vi.mock('@/admin/components/LiveFeed', () => ({ LiveFeed: () => <div /> }));
vi.mock('@/admin/components/SeedDemoButton', () => ({ SeedDemoButton: () => <div /> }));

import OverviewPage from '@/admin/pages/OverviewPage';

describe('admin overview privacy-safe operations surface', () => {
  it('shows aggregate readiness state without seeker or reviewer text', () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>);

    expect(screen.getByText('Launch readiness')).toBeInTheDocument();
    expect(screen.getByText('gemini-flash-budget-v1')).toBeInTheDocument();
    expect(screen.getByText('Staged')).toBeInTheDocument();
    expect(screen.queryByText(/private seeker question/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/private failure question/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/private review note/i)).not.toBeInTheDocument();
  });
});
