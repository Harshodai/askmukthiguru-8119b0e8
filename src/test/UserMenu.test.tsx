import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UserMenu } from '@/components/common/UserMenu';
import * as profileStorage from '@/lib/profileStorage';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('UserMenu', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockNavigate.mockClear();
  });

  it('renders trigger button with initials fallback when no avatar image is set', () => {
    const defaultProf = profileStorage.createDefaultProfile();
    defaultProf.displayName = 'Arjun Seeker';
    vi.spyOn(profileStorage, 'loadProfile').mockReturnValue(defaultProf);

    render(
      <MemoryRouter>
        <UserMenu />
      </MemoryRouter>
    );

    const trigger = screen.getByLabelText(/Open user menu/i);
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent('AS');
  });

  it('opens dropdown menu and renders menu items', async () => {
    const defaultProf = profileStorage.createDefaultProfile();
    defaultProf.displayName = 'Arjun Seeker';
    vi.spyOn(profileStorage, 'loadProfile').mockReturnValue(defaultProf);

    render(
      <MemoryRouter>
        <UserMenu />
      </MemoryRouter>
    );

    const trigger = screen.getByLabelText(/Open user menu/i);
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    fireEvent.keyDown(trigger, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('Arjun Seeker')).toBeInTheDocument();
    });

    expect(screen.getByText(/Settings/i)).toBeInTheDocument();
    expect(screen.getByText(/Security & privacy/i)).toBeInTheDocument();
    expect(screen.getByText(/Take a Tour/i)).toBeInTheDocument();
  });
});
