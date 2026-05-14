import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/admin/lib/filtersStore', () => ({
  useAdminFilters: () => ({
    filters: {
      preset: '24h',
      from: new Date('2026-01-01T00:00:00Z'),
      to: new Date('2026-01-02T00:00:00Z'),
    },
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
