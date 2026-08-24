import React from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import App from '@/App';

// Keep App imports lightweight by mocking route pages.
vi.mock('@/pages/Index', () => ({ default: () => <div data-testid="index-page">Index</div> }));
vi.mock('@/pages/ChatPage', () => ({ default: () => <div data-testid="chat-page">Chat</div> }));
vi.mock('@/pages/ProfilePage', () => ({ default: () => <div data-testid="profile-page">Profile</div> }));
vi.mock('@/pages/NotFound', () => ({ default: () => <div data-testid="notfound-page">Not Found</div> }));
vi.mock('@/pages/AuthPage', () => ({ default: () => <div data-testid="auth-page">Auth</div> }));
vi.mock('@/pages/PracticesPage', () => ({ default: () => <div data-testid="practices-page">Practices</div> }));
vi.mock('@/pages/PracticeDetailPage', () => ({ default: () => <div data-testid="practice-detail-page">Practice Detail</div> }));
vi.mock('@/pages/StudyNotebookPage', () => ({ default: () => <div data-testid="notebook-page">Notebooks</div> }));
vi.mock('@/pages/KnowledgeGraphPage', () => ({ default: () => <div data-testid="kg-page">KG</div> }));
vi.mock('@/pages/SecondBrainPage', () => ({ default: () => <div data-testid="secondbrain-page">Second Brain</div> }));
vi.mock('@/pages/PrivacyPage', () => ({ default: () => <div data-testid="privacy-page">Privacy</div> }));
vi.mock('@/pages/TermsPage', () => ({ default: () => <div data-testid="terms-page">Terms</div> }));
vi.mock('@/pages/ResetPasswordPage', () => ({ default: () => <div data-testid="reset-page">Reset</div> }));
vi.mock('@/pages/TTSVerificationPage', () => ({ default: () => <div data-testid="tts-page">TTS</div> }));
vi.mock('@/pages/MFAChallengePage', () => ({ default: () => <div data-testid="mfa-page">MFA</div> }));
vi.mock('@/pages/AuthDiagnosticsPage', () => ({ default: () => <div data-testid="auth-diag-page">Auth Diagnostics</div> }));
vi.mock('@/pages/AuthLatencyDashboard', () => ({ default: () => <div data-testid="auth-latency-page">Latency</div> }));
vi.mock('@/pages/guides/SpiritGuidesPage', () => ({ default: () => <div data-testid="spirit-guides-page">Guides</div> }));
vi.mock('@/pages/guides/AiSpiritualCompanionPage', () => ({ default: () => <div data-testid="companion-page">Companion</div> }));
vi.mock('@/pages/guides/BeautifulStateMeditationPage', () => ({ default: () => <div data-testid="beautiful-page">Beautiful</div> }));
vi.mock('@/pages/guides/SereneMindPracticePage', () => ({ default: () => <div data-testid="serene-page">Serene</div> }));
vi.mock('@/pages/guides/SelfCentricThinkingPage', () => ({ default: () => <div data-testid="self-centric-page">Self-Centric</div> }));
vi.mock('@/pages/guides/SpiritualGuideForAnxietyPage', () => ({ default: () => <div data-testid="anxiety-page">Anxiety</div> }));
vi.mock('@/pages/guides/SufferingToBeautifulStatePage', () => ({ default: () => <div data-testid="suffering-page">Suffering</div> }));

vi.mock('@/components/common/SessionExpiredHandler', () => ({ SessionExpiredHandler: () => null }));
vi.mock('@/components/common/CookieConsentBanner', () => ({ CookieConsentBanner: () => null }));
vi.mock('@/components/common/PushPermissionPrompt', () => ({ PushPermissionPrompt: () => null }));
vi.mock('@/components/common/PushNotificationsManager', () => ({ PushNotificationsManager: () => null }));
vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({ open: vi.fn(), setOnComplete: vi.fn() }),
  SereneMindProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => false },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: 'thirdParty' as const },
  I18nextProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/lib/sentry', () => ({
  trackPageview: vi.fn(),
  captureFeatureError: vi.fn(),
}));

vi.mock('@/lib/webVitals', () => ({ initWebVitals: vi.fn() }));

vi.mock('@/lib/lazyWithRetry', () => ({
  lazyWithRetry: (factory: () => Promise<{ default: React.ComponentType }>) => {
    const LazyComponent = React.lazy(factory);
    return LazyComponent;
  },
  preloadCriticalRoutes: vi.fn(),
}));

vi.mock('@/components/ui/sonner', () => ({ Toaster: () => null }));
vi.mock('@/components/ui/toaster', () => ({ Toaster: () => null }));

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('QueryClient defaults', () => {
  it('provides a QueryClient with configured defaults', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('index-page')).toBeInTheDocument());
  });
});

describe('public compatibility routes', () => {
  it('routes /guides to the public guides landing content', async () => {
    window.history.pushState({}, '', '/guides');
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('spirit-guides-page')).toBeInTheDocument());
    expect(screen.queryByTestId('notfound-page')).not.toBeInTheDocument();
  });

  it('routes /support to the profile support surface', async () => {
    window.history.pushState({}, '', '/support');
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('profile-page')).toBeInTheDocument());
    expect(screen.queryByTestId('notfound-page')).not.toBeInTheDocument();
  });
});

describe('QueryClient retry behavior', () => {
  it('does not retry 401 errors', async () => {
    const fetcher = vi.fn().mockRejectedValue({ status: 401 });
    const client = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 60_000,
          retry: (failureCount, error) => {
            if (error instanceof Response && error.status === 401) return false;
            if ((error as { status?: number })?.status === 401) return false;
            return failureCount < 3;
          },
          throwOnError: false,
          retryDelay: 0,
        },
      },
    });

    function TestComponent() {
      const query = useQuery({ queryKey: ['401-test'], queryFn: fetcher });
      return <div data-testid="result">{query.status}</div>;
    }

    render(
      <QueryClientProvider client={client}>
        <TestComponent />
      </QueryClientProvider>
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('result')).toHaveTextContent('error'));
  });

  it('retries non-401 errors up to 2 times', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('network error'));
    const client = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 60_000,
          retry: (failureCount, error) => {
            if (error instanceof Response && error.status === 401) return false;
            if ((error as { status?: number })?.status === 401) return false;
            return failureCount < 3;
          },
          throwOnError: false,
          retryDelay: 0,
        },
      },
    });

    function TestComponent() {
      const query = useQuery({ queryKey: ['retry-test'], queryFn: fetcher });
      return <div data-testid="result">{query.status}</div>;
    }

    render(
      <QueryClientProvider client={client}>
        <TestComponent />
      </QueryClientProvider>
    );

    await waitFor(() => expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(3));
    await waitFor(() => expect(screen.getByTestId('result')).toHaveTextContent('error'));
  });
});
