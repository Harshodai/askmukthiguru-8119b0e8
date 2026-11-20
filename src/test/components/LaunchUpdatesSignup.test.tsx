import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const { rpcMock } = vi.hoisted(() => ({ rpcMock: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { rpc: rpcMock },
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
    rpcMock.mockReset();
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
    expect(rpcMock).not.toHaveBeenCalled();
  });

  it('shows a pending state, then success', async () => {
    let resolveRpc!: (value: { data: string; error: null }) => void;
    rpcMock.mockReturnValue(
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

    resolveRpc({ data: 'accepted', error: null });
    expect(await screen.findByRole('status')).toHaveTextContent(/on the launch list/i);
    expect(rpcMock).toHaveBeenCalledWith('subscribe_launch_updates', {
      p_email: 'seeker@example.com',
      p_consent: true,
      p_source: 'guide_ai_spiritual_companion',
    });
  });

  it('keeps the typed email after a failure and retries successfully', async () => {
    rpcMock.mockResolvedValueOnce({ data: null, error: { message: 'Signup temporarily busy' } });

    renderForm();
    const email = screen.getByLabelText('Email address');
    fireEvent.change(email, { target: { value: 'Seeker@Example.com' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/try again/i);
    expect(alert).not.toHaveTextContent(/seeker@example\.com/i);
    expect(email).toHaveValue('Seeker@Example.com');

    rpcMock.mockResolvedValueOnce({ data: 'accepted', error: null });
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));
    expect(await screen.findByRole('status')).toBeInTheDocument();
    expect(rpcMock).toHaveBeenCalledTimes(2);
  });

  it('rejects a malformed address before any request', async () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Join launch list' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/valid email/i));
    expect(rpcMock).not.toHaveBeenCalled();
  });
});
