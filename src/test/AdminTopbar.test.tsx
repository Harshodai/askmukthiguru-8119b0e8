import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/admin/lib/filtersStore', () => ({
  useAdminFilters: () => ({
    filters: { preset: '24h', range: { from: new Date(), to: new Date() } },
    setPreset: vi.fn(),
    setRange: vi.fn(),
    refresh: vi.fn(),
  }),
}));

import { AdminTopbar } from '@/admin/layout/AdminTopbar';

describe('AdminTopbar', () => {
  it('shows the Role Verified badge so admins can confirm RPC-backed access', () => {
    render(<AdminTopbar />);
    expect(screen.getByText(/Role Verified/i)).toBeInTheDocument();
  });
});
