import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const { rpcMock } = vi.hoisted(() => ({ rpcMock: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: rpcMock } }));
vi.mock('@/components/layout/PublicShell', () => ({
  PublicShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { submitLaunchErase } from '@/lib/launchUpdates';
import { LaunchUpdatesSignup } from '@/components/guides/LaunchUpdatesSignup';
import UnsubscribePage from '@/pages/UnsubscribePage';

const locale = (code: string) =>
  JSON.parse(readFileSync(join(__dirname, '..', 'locales', `${code}.json`), 'utf8'));

describe('launch updates erase path', () => {
  beforeEach(() => rpcMock.mockReset());

  it('sends only the normalized email and never echoes it', async () => {
    rpcMock.mockResolvedValue({ data: 'accepted', error: null });
    const result = await submitLaunchErase('  Seeker@Example.COM ');
    expect(result).toEqual({ status: 'accepted' });
    expect(rpcMock).toHaveBeenCalledWith('erase_launch_subscription', { p_email: 'seeker@example.com' });
    expect(JSON.stringify(result)).not.toContain('seeker');
  });

  it('does not call the database for a malformed address, and maps errors to one failure', async () => {
    expect(await submitLaunchErase('nope')).toEqual({ status: 'failed', reason: 'invalid_email' });
    expect(rpcMock).not.toHaveBeenCalled();
    rpcMock.mockResolvedValue({ data: null, error: { message: 'Signup temporarily busy' } });
    expect(await submitLaunchErase('seeker@example.com')).toEqual({ status: 'failed', reason: 'request_failed' });
  });
});

describe('consent copy and unsubscribe UI', () => {
  beforeEach(() => rpcMock.mockReset());

  it('states purpose, 12-month retention, withdrawal and links to privacy and unsubscribe', () => {
    render(
      <MemoryRouter>
        <LaunchUpdatesSignup source="guide_serene_mind" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Used only for launch updates\. Kept for up to 12 months/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Privacy' }).getAttribute('href')).toBe('/privacy');
    expect(screen.getByRole('link', { name: /Unsubscribe and erase/ }).getAttribute('href')).toBe('/unsubscribe');
    expect((screen.getByRole('checkbox') as HTMLInputElement).getAttribute('aria-checked')).toBe('false');
  });

  it('erases and shows the same neutral confirmation', async () => {
    rpcMock.mockResolvedValue({ data: 'accepted', error: null });
    render(
      <MemoryRouter>
        <UnsubscribePage />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'seeker@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Erase my email' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).toMatch(/If that address was on the launch list/));
    expect(rpcMock).toHaveBeenCalledTimes(1);
  });

  it('shows an error and keeps the form when the request fails', async () => {
    rpcMock.mockResolvedValue({ data: null, error: { message: 'x' } });
    render(
      <MemoryRouter>
        <UnsubscribePage />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'seeker@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Erase my email' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
  });
});

describe('locale coverage of the launch consent copy', () => {
  const keys: Array<[string, string]> = [
    ['launchUpdates', 'consentLabel'],
    ['launchUpdates', 'notice'],
    ['unsubscribe', 'done'],
    ['privacy', 'launchText'],
  ];
  it.each(['hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'as', 'sa', 'or', 'pa', 'ur'])(
    '%s has its own non-English consent, notice and privacy text',
    (code) => {
      const en = locale('en');
      const loc = locale(code);
      for (const [group, key] of keys) {
        expect(loc[group][key]).toBeTruthy();
        expect(loc[group][key]).not.toBe(en[group][key]);
        // The retention period must survive translation wherever English states it.
        if (/12/.test(en[group][key])) expect(loc[group][key]).toMatch(/12/);
      }
    },
  );
});
