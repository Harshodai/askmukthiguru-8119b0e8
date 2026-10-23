import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProfilePage from '@/pages/ProfilePage';
import * as profileStorage from '@/lib/profileStorage';

// Mock dependencies for ProfilePage
vi.mock('@/hooks/useRequireAuth', () => ({
  useRequireAuth: () => ({
    loading: false,
    user: { id: 'u1', email: 'seeker@example.com', user_metadata: { full_name: 'Test Seeker' } },
  }),
}));

vi.mock('@/hooks/useDailyTeaching', () => ({
  useDailyTeaching: () => ({ teaching: null, loading: false }),
}));

vi.mock('@/hooks/useMetrics', () => ({
  useMetrics: () => ({ metrics: null, loading: false, error: null }),
}));

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div data-testid="app-shell">{children}</div>,
}));

vi.mock('@/components/profile/NotesPanel', () => ({
  NotesPanel: () => <div data-testid="notes-panel">Notes</div>,
}));

vi.mock('@/components/profile/MemoryManager', () => ({
  MemoryManager: () => <div data-testid="memory-manager">Memories</div>,
}));

describe('ProfilePage Draft Preservation & Sticky Save Action', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('preserves draft input across theme changes and shows clear device-level save status', async () => {
    render(
      <MemoryRouter initialEntries={['/profile?tab=profile']}>
        <Routes>
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </MemoryRouter>
    );

    // Initial state: not dirty -> "Saved on this device."
    expect(screen.getByText('Saved on this device.')).toBeInTheDocument();
    const saveButton = screen.getByRole('button', { name: /Save Changes/i });
    expect(saveButton).toBeDisabled();

    // Modify displayName draft
    const nameInput = screen.getByLabelText(/Display Name/i);
    fireEvent.change(nameInput, { target: { value: 'Enlightened Seeker' } });

    // Now dirty -> displays "Unsaved changes..."
    expect(screen.getByText('Unsaved changes...')).toBeInTheDocument();
    expect(saveButton).not.toBeDisabled();

    // Switch to Settings tab
    const settingsTab = screen.getByRole('tab', { name: /Settings/i });
    fireEvent.pointerDown(settingsTab, { button: 0, pointerId: 1 });
    fireEvent.click(settingsTab);
    fireEvent.keyDown(settingsTab, { key: 'Enter' });

    // Wait for Settings tab content to appear
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Dark/i })).toBeInTheDocument();
    });

    // Draft is preserved and sticky save action still reflects unsaved changes
    expect(screen.getByText('Unsaved changes...')).toBeInTheDocument();
    const saveButtonInSettings = screen.getByRole('button', { name: /Save Changes/i });
    expect(saveButtonInSettings).toBeInTheDocument();
    expect(saveButtonInSettings).toBeEnabled();

    // Click Dark theme button
    const darkThemeButton = screen.getByRole('button', { name: /Dark/i });
    fireEvent.click(darkThemeButton);

    // Switch back to Profile / Personalise tab
    const personaliseTab = screen.getByRole('tab', { name: /Personalise/i });
    fireEvent.pointerDown(personaliseTab, { button: 0, pointerId: 1 });
    fireEvent.click(personaliseTab);
    fireEvent.keyDown(personaliseTab, { key: 'Enter' });

    // Wait for Personalise tab to become active
    await waitFor(() => {
      expect(screen.getByLabelText(/Display Name/i)).toBeInTheDocument();
    });

    // Verify displayName draft was preserved across the theme switch
    const recheckedNameInput = screen.getByLabelText(/Display Name/i) as HTMLInputElement;
    expect(recheckedNameInput.value).toBe('Enlightened Seeker');

    // Click Save Changes
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

    // Status returns to "Saved on this device."
    await waitFor(() => {
      expect(screen.getByText('Saved on this device.')).toBeInTheDocument();
    });
  });

  it('preserves draft text when an avatar file is updated', async () => {
    render(
      <MemoryRouter initialEntries={['/profile?tab=profile']}>
        <Routes>
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </MemoryRouter>
    );

    const bioInput = screen.getByLabelText(/Your Path & Intention/i);
    fireEvent.change(bioInput, { target: { value: 'Seeking inner stillness and the beautiful state.' } });

    expect(screen.getByText('Unsaved changes...')).toBeInTheDocument();

    // Trigger mock avatar pick
    vi.spyOn(profileStorage, 'readAvatarFile').mockResolvedValue('data:image/png;base64,mockAvatar');
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['avatar content'], 'avatar.png', { type: 'image/png' });

    fireEvent.change(fileInput, { target: { files: [file] } });

    // Wait for observable avatar change (e.g. Remove photo action appears)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Remove photo/i })).toBeInTheDocument();
    });

    // Verify draft bio is NOT lost
    const recheckedBio = screen.getByLabelText(/Your Path & Intention/i) as HTMLTextAreaElement;
    expect(recheckedBio.value).toBe('Seeking inner stillness and the beautiful state.');
    expect(screen.getByText('Unsaved changes...')).toBeInTheDocument();
  });
});
