import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import ProfilePage from './ProfilePage';

// Mock all necessary hooks and components
vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: {
      id: 'test-id',
      name: 'Test User',
      displayName: 'Test User',
      bio: '',
      email: 'test@example.com',
      avatarUrl: null,
      preferredLanguage: 'en',
      guruTone: 'gentle',
      theme: 'system',
      primaryGoal: 'peace',
      experienceLevel: 'beginner',
      preferredStyle: 'direct',
      spiritualBackground: 'none',
      challengeAreas: [],
      meditationReminderTime: '08:00',
      meditationReminderEnabled: false,
    },
    updateProfile: vi.fn().mockResolvedValue(undefined),
    uploadAvatar: vi.fn(),
    removeAvatar: vi.fn(),
    deleteEverything: vi.fn(),
    exportData: vi.fn(),
    isLoading: false,
    isSaving: false,
  }),
}));

vi.mock('@/hooks/usePageMeta', () => ({
  usePageMeta: vi.fn(),
}));

vi.mock('@/hooks/useTheme', () => ({
  useTheme: () => ({
    theme: 'light',
    setTheme: vi.fn(),
  }),
}));

vi.mock('@/hooks/useRequireAuth', () => ({
  useRequireAuth: () => ({ loading: false }),
}));

vi.mock('@/lib/auth', () => ({
  useAuth: () => ({
    user: { id: 'test-id', email: 'test@example.com' },
  }),
}));

vi.mock('@/hooks/useMeditationReminder', () => ({
  fireTestReminder: vi.fn(),
  requestNotificationPermission: vi.fn().mockResolvedValue('granted'),
}));

// Mock framer-motion to bypass animations
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');
  return {
    ...actual,
    motion: {
      div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode }) =>
        <div {...props}>{children}</div>,
      p: ({ children, ...props }: React.HTMLAttributes<HTMLParagraphElement> & { children?: React.ReactNode }) =>
        <p {...props}>{children}</p>,
      form: ({ children, ...props }: React.HTMLAttributes<HTMLFormElement> & { children?: React.ReactNode }) =>
        <form {...props}>{children}</form>,
    },
  };
});

describe('ProfilePage', () => {
  it('renders without crashing', () => {
    render(
      <BrowserRouter>
        <ProfilePage />
      </BrowserRouter>
    );

    // Check if profile header or name is rendered
    expect(screen.getByText('Test User')).toBeInTheDocument();
  });
});
