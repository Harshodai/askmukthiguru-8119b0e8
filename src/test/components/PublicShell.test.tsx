import { render, screen } from '@testing-library/react';
import { PublicShell } from '@/components/layout/PublicShell';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';

describe('PublicShell', () => {
  it('renders children without requiring auth', () => {
    render(
      <MemoryRouter>
        <PublicShell title="Public page">
          <div data-testid="public-content">Hello</div>
        </PublicShell>
      </MemoryRouter>
    );
    expect(screen.getByTestId('public-content')).toBeInTheDocument();
  });
});
