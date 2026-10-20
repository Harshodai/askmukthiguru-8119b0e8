import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ createNote: vi.fn(), updateNote: vi.fn(), deleteNote: vi.fn(), toast: vi.fn() }));
vi.mock('@/hooks/useNotes', () => ({ useNotes: () => ({ notes: [], loading: false, error: null, refresh: vi.fn(), ...mocks }) }));
vi.mock('@/hooks/use-toast', () => ({ toast: mocks.toast }));
vi.mock('@/hooks/useSpeechRecognition', () => ({ useSpeechRecognition: () => ({ isSupported: false, isListening: false }) }));
import { NotesPanel } from '@/components/profile/NotesPanel';

describe('NotesPanel confirmed persistence', () => {
  beforeEach(() => vi.clearAllMocks());
  const compose = () => {
    render(<MemoryRouter><NotesPanel /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /new note/i }));
    fireEvent.change(screen.getByRole('textbox', { name: '' , multiline: true }), { target: { value: 'My reflection after practice' } });
    fireEvent.click(screen.getByRole('button', { name: /save note/i }));
  };

  it('keeps a failed save draft open without announcing success', async () => {
    mocks.createNote.mockResolvedValue(null);
    compose();
    await waitFor(() => expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' })));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByDisplayValue('My reflection after practice')).toBeInTheDocument();
    expect(mocks.toast).toHaveBeenCalledTimes(1);
  });

  it('closes the draft only after a confirmed write', async () => {
    mocks.createNote.mockResolvedValue({ id: 'saved-note' });
    compose();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mocks.createNote).toHaveBeenCalledWith(expect.objectContaining({ body: 'My reflection after practice' }));
    expect(mocks.toast).toHaveBeenCalledTimes(1);
    expect(mocks.toast.mock.calls[0][0].variant).toBeUndefined();
  });
});