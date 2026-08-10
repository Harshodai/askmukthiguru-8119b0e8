import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Outlet } from 'react-router-dom';
import { Suspense, lazy, type ComponentType } from 'react';
import { AdminErrorBoundary } from '@/admin/components/AdminErrorBoundary';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

// Wraps each lazy admin child route in its own Suspense + error boundary —
// mirrors the App.tsx AdminRoute arrangement (P1-AI-19).
const AdminRoute = ({ children }: { children: React.ReactNode }) => (
  <AdminErrorBoundary>
    <Suspense fallback={<div>admin-loading</div>}>{children}</Suspense>
  </AdminErrorBoundary>
);

const AdminRoutes = ({ children }: { children: React.ReactNode }) => (
  <Routes>
    <Route path="/admin" element={<div>admin-shell<Outlet /></div>}>
      {children}
    </Route>
  </Routes>
);

describe('AdminRoute per-route suspension (P1-AI-19)', () => {
  it('a crashing lazy route renders the error boundary without unmounting the shell', async () => {
    const OverviewPage = lazy(async () => {
      throw new Error('overview chunk failed to load');
    });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminRoutes>
          <Route index element={<AdminRoute><OverviewPage /></AdminRoute>} />
        </AdminRoutes>
      </MemoryRouter>,
    );

    await screen.findByText(/something went wrong/i);
    expect(screen.getByText('admin-shell')).toBeInTheDocument();
    expect(screen.queryByText('admin-loading')).not.toBeInTheDocument();
  });

  it('a pending lazy route shows its own fallback while the shell stays mounted', async () => {
    let resolvePending!: (value: { default: ComponentType }) => void;
    const pending = new Promise<{ default: ComponentType }>((res) => {
      resolvePending = res;
    });
    const QueriesPage = lazy(async () => {
      const mod = await pending;
      return mod;
    });

    render(
      <MemoryRouter initialEntries={['/admin/queries']}>
        <AdminRoutes>
          <Route path="queries" element={<AdminRoute><QueriesPage /></AdminRoute>} />
        </AdminRoutes>
      </MemoryRouter>,
    );

    expect(screen.getByText('admin-shell')).toBeInTheDocument();
    expect(screen.getByText('admin-loading')).toBeInTheDocument();

    resolvePending({ default: () => <div>queries-loaded</div> });
    await screen.findByText('queries-loaded');
    expect(screen.getByText('admin-shell')).toBeInTheDocument();
  });

  it('a crashing route does not take down a sibling route that already loaded', async () => {
    const OverviewPage = lazy(async () => {
      throw new Error('overview chunk failed to load');
    });
    const QueriesPage = lazy(async () => ({ default: () => <div>queries-loaded</div> }));
    const routes = (
      <>
        <Route index element={<AdminRoute><OverviewPage /></AdminRoute>} />
        <Route path="queries" element={<AdminRoute><QueriesPage /></AdminRoute>} />
      </>
    );

    const first = render(
      <MemoryRouter initialEntries={['/admin/queries']}>
        <AdminRoutes>{routes}</AdminRoutes>
      </MemoryRouter>,
    );
    await screen.findByText('queries-loaded');

    const second = render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminRoutes>{routes}</AdminRoutes>
      </MemoryRouter>,
    );
    await second.findByText(/something went wrong/i);
    first.unmount();
    expect(second.getByText('admin-shell')).toBeInTheDocument();
    second.unmount();

    const third = render(
      <MemoryRouter initialEntries={['/admin/queries']}>
        <AdminRoutes>{routes}</AdminRoutes>
      </MemoryRouter>,
    );
    await third.findByText('queries-loaded');
    expect(third.getByText('admin-shell')).toBeInTheDocument();
  });
});
