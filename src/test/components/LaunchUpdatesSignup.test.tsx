import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { functions: { invoke: invokeMock } },
}));

import { LaunchUpdatesSignup } from '@/components/guides/LaunchUpdatesSignup';

const renderForm = () =>
  render(
    <MemoryRouter>
      <LaunchUpdatesSignup source="guide_ai_spiritual_companion" />
    </MemoryRouter>,
  );

describe('LaunchUpdatesSignup', () => {
  beforeEach(() => {
    invokeMock.mockReset();
  });

  it('has a visible email label and an unchecked consent box', () => {
    renderForm();
    expect(screen.getByText('Email address', { selector: 'label' })).toBeInTheDocument();
    expect(screen.getByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy');
  });

  it('refuses to submit without contact consent and makes no request', async () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'seeker@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/confirm/i);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('shows a pending state, then success', async () => {
    let resolveRpc: ((value: { data: { status: string }; error: null }) => void) | undefined;
    invokeMock.mockReturnValue(
      new Promise((resolve) => {
        resolveRpc = resolve;
      }),
    );

    renderForm();
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'seeker@example.com' },
    });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));

    const pending = screen.getByRole('button', { name: 'Joining…' });
    expect(pending).toBeDisabled();
    expect(pending).toHaveAttribute('aria-busy', 'true');

    resolveRpc?.({ data: { status: 'accepted' }, error: null });
    expect(await screen.findByRole('status')).toHaveTextContent(/on the launch list/i);
    expect(invokeMock).toHaveBeenCalledWith('launch-signup', { body: {
      email: 'seeker@example.com',
      consent: true,
      source: 'guide_ai_spiritual_companion',
    } });
  });

  it('keeps the typed email after a failure and retries successfully', async () => {
    invokeMock.mockResolvedValueOnce({ data: null, error: { message: 'Signup temporarily busy' } });

    renderForm();
    const email = screen.getByLabelText('Email address');
    fireEvent.change(email, { target: { value: 'Seeker@Example.com' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/try again/i);
    expect(alert).not.toHaveTextContent(/seeker@example\.com/i);
    expect(email).toHaveValue('Seeker@Example.com');

    invokeMock.mockResolvedValueOnce({ data: { status: 'accepted' }, error: null });
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));
    expect(await screen.findByRole('status')).toBeInTheDocument();
    expect(invokeMock).toHaveBeenCalledTimes(2);
  });

  it('rejects a malformed address before any request', async () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/valid email/i));
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
