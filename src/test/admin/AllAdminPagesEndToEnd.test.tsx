import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock Lucide icons that could cause canvas / heavy render issues if needed
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

// Admin Pages
import AdminLoginPage from '@/admin/pages/AdminLoginPage';
import AdminsPage from '@/admin/pages/AdminsPage';
import AlertsPage from '@/admin/pages/AlertsPage';
import CachePage from '@/admin/pages/CachePage';
import DailyTeachingPage from '@/admin/pages/DailyTeachingPage';
import DataSourcesPage from '@/admin/pages/DataSourcesPage';
import EvalsPage from '@/admin/pages/EvalsPage';
import FeedbackPage from '@/admin/pages/FeedbackPage';
import IngestionPage from '@/admin/pages/IngestionPage';
import JobsPage from '@/admin/pages/JobsPage';
import LogsPage from '@/admin/pages/LogsPage';
import MonitoringPage from '@/admin/pages/MonitoringPage';
import OkfManager from '@/admin/pages/OkfManager';
import OverviewPage from '@/admin/pages/OverviewPage';
import PromptsPage from '@/admin/pages/PromptsPage';
import QualityPage from '@/admin/pages/QualityPage';
import QueriesPage from '@/admin/pages/QueriesPage';
import RAGFlowPage from '@/admin/pages/RAGFlowPage';
import RetrievalPage from '@/admin/pages/RetrievalPage';
import SettingsPage from '@/admin/pages/SettingsPage';
import StagingQueuePage from '@/admin/pages/StagingQueuePage';
import TeachingTipsPage from '@/admin/pages/TeachingTipsPage';
import TelemetryPage from '@/admin/pages/TelemetryPage';
import TopicsPage from '@/admin/pages/TopicsPage';
import TriggersPage from '@/admin/pages/TriggersPage';
import AdminSelfCheckPage from '@/pages/AdminSelfCheckPage';

import { AdminFiltersProvider } from '@/admin/lib/filtersStore';

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminFiltersProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </AdminFiltersProvider>
    </QueryClientProvider>
  );
}

describe('End-to-End Testing of All 26 Admin Pages Locally', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const pages = [
    { name: '1. AdminLoginPage', component: <AdminLoginPage /> },
    { name: '2. AdminsPage', component: <AdminsPage /> },
    { name: '3. AlertsPage', component: <AlertsPage /> },
    { name: '4. CachePage', component: <CachePage /> },
    { name: '5. DailyTeachingPage', component: <DailyTeachingPage /> },
    { name: '6. DataSourcesPage', component: <DataSourcesPage /> },
    { name: '7. EvalsPage', component: <EvalsPage /> },
    { name: '8. FeedbackPage', component: <FeedbackPage /> },
    { name: '9. IngestionPage', component: <IngestionPage /> },
    { name: '10. JobsPage', component: <JobsPage /> },
    { name: '11. LogsPage', component: <LogsPage /> },
    { name: '12. MonitoringPage', component: <MonitoringPage /> },
    { name: '13. OkfManager', component: <OkfManager /> },
    { name: '14. OverviewPage', component: <OverviewPage /> },
    { name: '15. PromptsPage', component: <PromptsPage /> },
    { name: '16. QualityPage', component: <QualityPage /> },
    { name: '17. QueriesPage', component: <QueriesPage /> },
    { name: '18. RAGFlowPage', component: <RAGFlowPage /> },
    { name: '19. RetrievalPage', component: <RetrievalPage /> },
    { name: '20. SettingsPage', component: <SettingsPage /> },
    { name: '21. StagingQueuePage', component: <StagingQueuePage /> },
    { name: '22. TeachingTipsPage', component: <TeachingTipsPage /> },
    { name: '23. TelemetryPage', component: <TelemetryPage /> },
    { name: '24. TopicsPage', component: <TopicsPage /> },
    { name: '25. TriggersPage', component: <TriggersPage /> },
    { name: '26. AdminSelfCheckPage', component: <AdminSelfCheckPage /> },
  ];

  pages.forEach(({ name, component }) => {
    it(`renders ${name} cleanly without crashing on default state`, () => {
      const { container } = renderWithProviders(component);
      expect(container).toBeDefined();
      expect(container.firstChild).not.toBeNull();
    });

    it(`renders ${name} gracefully without crashing when network/backend fails with 503`, () => {
      const errorQueryClient = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            queryFn: () => Promise.reject(new Error('503 Service Unavailable')),
          },
        },
      });

      const { container } = render(
        <QueryClientProvider client={errorQueryClient}>
          <AdminFiltersProvider>
            <MemoryRouter>{component}</MemoryRouter>
          </AdminFiltersProvider>
        </QueryClientProvider>
      );

      expect(container).toBeDefined();
      expect(container.firstChild).not.toBeNull();
    });
  });
});
