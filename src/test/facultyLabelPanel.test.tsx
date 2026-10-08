import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const { upsert, getUser, incognito } = vi.hoisted(() => ({
  upsert: vi.fn(),
  getUser: vi.fn(),
  incognito: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: { getUser },
    from: vi.fn(() => ({ upsert })),
  },
}));
vi.mock('@/lib/chatStorage', () => ({ isIncognitoMode: incognito }));

import { FacultyLabelPanel } from '@/components/chat/FacultyLabelPanel';
import { buildFacultyLabelRow } from '@/lib/facultyLabels';

const manifest = { release_id: 'rel-1', policy_version: 'pol-7', schema_version: 's1' };

function fillAll() {
  fireEvent.click(screen.getByRole('radio', { name: 'Partly' }));
  fireEvent.click(screen.getByRole('radio', { name: 'Safe yes' }));
  fireEvent.click(screen.getByRole('radio', { name: 'Helpful 4' }));
}

describe('FacultyLabelPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    incognito.mockReturnValue(false);
    getUser.mockResolvedValue({ data: { user: { id: 'user-a' } } });
    upsert.mockResolvedValue({ error: null });
  });

  it('keeps Save disabled until faithful, safe and helpful are all chosen', () => {
    render(<FacultyLabelPanel traceId="t1" model="m" releaseManifest={manifest} />);
    const save = screen.getByRole('button', { name: 'Save label' });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: 'Partly' }));
    fireEvent.click(screen.getByRole('radio', { name: 'Safe yes' }));
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: 'Helpful 4' }));
    expect(save).toBeEnabled();
  });

  it('upserts the label with trace, model, policy id and user id', async () => {
    const onSubmitted = vi.fn();
    render(<FacultyLabelPanel traceId="t1" model="deepseek" releaseManifest={manifest} onSubmitted={onSubmitted} />);
    fillAll();
    fireEvent.change(screen.getByLabelText('Reviewer note'), { target: { value: '  paraphrase drifts  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save label' }));
    await waitFor(() => expect(screen.getByTestId('faculty-label-saved')).toBeInTheDocument());
    const [row, opts] = upsert.mock.calls[0];
    expect(opts).toEqual({ onConflict: 'user_id,answer_key' });
    expect(row).toMatchObject({
      user_id: 'user-a',
      trace_id: 't1',
      model: 'deepseek',
      policy_id: 'pol-7',
      release_id: 'rel-1',
      faithful: 'partly',
      safe: true,
      helpful: 4,
      note: 'paraphrase drifts',
    });
    expect(onSubmitted).toHaveBeenCalled();
  });

  it('refuses to label an answer with no trace_id or request_id', () => {
    render(<FacultyLabelPanel />);
    fillAll();
    expect(screen.getByRole('button', { name: 'Save label' })).toBeDisabled();
    expect(screen.getByText(/no trace id/i)).toBeInTheDocument();
  });

  it('surfaces a save error and does not claim success', async () => {
    upsert.mockResolvedValue({ error: { message: 'permission denied' } });
    render(<FacultyLabelPanel requestId="r1" />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Save label' }));
    await waitFor(() => expect(screen.getByTestId('faculty-label-error')).toHaveTextContent('permission denied'));
    expect(screen.queryByTestId('faculty-label-saved')).toBeNull();
  });

  it('sends nothing in incognito mode', async () => {
    incognito.mockReturnValue(true);
    render(<FacultyLabelPanel traceId="t1" />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Save label' }));
    await waitFor(() => expect(screen.getByTestId('faculty-label-error')).toBeInTheDocument());
    expect(upsert).not.toHaveBeenCalled();
  });

  it('does not write when signed out', async () => {
    getUser.mockResolvedValue({ data: { user: null } });
    render(<FacultyLabelPanel traceId="t1" />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Save label' }));
    await waitFor(() => expect(screen.getByTestId('faculty-label-error')).toBeInTheDocument());
    expect(upsert).not.toHaveBeenCalled();
  });
});

describe('buildFacultyLabelRow', () => {
  it('falls back to release_id for policy_id and rejects out-of-range helpful', () => {
    const row = buildFacultyLabelRow(
      'u',
      { requestId: 'r', releaseManifest: { release_id: 'rel-9' } },
      { faithful: 'yes', safe: false, helpful: 1 },
    );
    expect(row.policy_id).toBe('rel-9');
    expect(row.trace_id).toBeNull();
    expect(() =>
      buildFacultyLabelRow('u', { traceId: 't' }, { faithful: 'yes', safe: true, helpful: 6 }),
    ).toThrow();
  });
});
