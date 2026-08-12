import { useEffect, Suspense, type ComponentType, type ReactNode } from "react";
import { lazyWithRetry, preloadCriticalRoutes } from "@/lib/lazyWithRetry";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, HashRouter, Routes, Route, Outlet, useLocation } from "react-router-dom";
import { Capacitor } from "@capacitor/core";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { SessionExpiredHandler } from "@/components/common/SessionExpiredHandler";
import { CookieConsentBanner } from "@/components/common/CookieConsentBanner";
import { BrandedSpinner } from "@/components/common/BrandedSpinner";
import { AdminErrorBoundary } from "@/admin/components/AdminErrorBoundary";
import { ChatErrorBoundary } from "@/components/common/ChatErrorBoundary";
import { SereneMindProvider } from "@/components/common/SereneMindProvider";
import { PushPermissionPrompt } from "@/components/common/PushPermissionPrompt";
import { PushNotificationsManager } from "@/components/common/PushNotificationsManager";
import { purgeConversationsByAge, getRetentionDays } from "@/lib/chatStorage";
import { trackPageview, captureFeatureError } from "@/lib/sentry";

// Pages
const Index = lazyWithRetry(() => import("./pages/Index"));
const ChatPage = lazyWithRetry(() => import("./pages/ChatPage"));
const ProfilePage = lazyWithRetry(() => import("./pages/ProfilePage"));
const PracticesPage = lazyWithRetry(() => import("./pages/PracticesPage"));
const PracticeDetailPage = lazyWithRetry(() => import("./pages/PracticeDetailPage"));
const NotFound = lazyWithRetry(() => import("./pages/NotFound"));
const AuthPage = lazyWithRetry(() => import("./pages/AuthPage"));
const MFAChallengePage = lazyWithRetry(() => import("./pages/MFAChallengePage"));
const AuthDiagnosticsPage = lazyWithRetry(() => import("./pages/AuthDiagnosticsPage"));
const AuthLatencyDashboard = lazyWithRetry(() => import("./pages/AuthLatencyDashboard"));
const ResetPasswordPage = lazyWithRetry(() => import("./pages/ResetPasswordPage"));
const PrivacyPage = lazyWithRetry(() => import("./pages/PrivacyPage"));
const TermsPage = lazyWithRetry(() => import("./pages/TermsPage"));
const TTSVerificationPage = lazyWithRetry(() => import("./pages/TTSVerificationPage"));
const SpiritGuidesPage = lazyWithRetry(() => import("./pages/guides/SpiritGuidesPage"));
const AiSpiritualCompanionPage = lazyWithRetry(() => import("./pages/guides/AiSpiritualCompanionPage"));
const BeautifulStateMeditationPage = lazyWithRetry(() => import("./pages/guides/BeautifulStateMeditationPage"));
const SereneMindPracticePage = lazyWithRetry(() => import("./pages/guides/SereneMindPracticePage"));
const SelfCentricThinkingPage = lazyWithRetry(() => import("./pages/guides/SelfCentricThinkingPage"));
const SpiritualGuideForAnxietyPage = lazyWithRetry(() => import("./pages/guides/SpiritualGuideForAnxietyPage"));
const SufferingToBeautifulStatePage = lazyWithRetry(() => import("./pages/guides/SufferingToBeautifulStatePage"));
const StudyNotebookPage = lazyWithRetry(() => import("./pages/StudyNotebookPage"));
const KnowledgeGraphPage = lazyWithRetry(() => import("./pages/KnowledgeGraphPage"));
const SecondBrainPage = lazyWithRetry(() => import("./pages/SecondBrainPage"));

// Admin — gated by VITE_ADMIN_ENABLED (default true). Set to 'false' to strip
// admin routes + page chunks from the production bundle. Vite replaces
// import.meta.env.VITE_ADMIN_ENABLED at build time, so when it's 'false' the
// entire block below is dead code and gets tree-shaken (no admin route path
// strings, no admin chunk imports).
const ADMIN_ENABLED = import.meta.env.VITE_ADMIN_ENABLED !== 'false';
const NoopPage: ComponentType = () => null;
declare global {
  interface Window {
    retryRetentionPurge?: () => void;
  }
}

let AdminLoginPage: ComponentType = NoopPage;
let AdminShell: ComponentType<{ children?: ReactNode }> = NoopPage;
let OverviewPage: ComponentType = NoopPage;
let QueriesPage: ComponentType = NoopPage;
let QualityPage: ComponentType = NoopPage;
let RetrievalPage: ComponentType = NoopPage;
let DailyTeachingPage: ComponentType = NoopPage;
let TeachingTipsPage: ComponentType = NoopPage;
let TriggersPage: ComponentType = NoopPage;
let TopicsPage: ComponentType = NoopPage;
let PromptsPage: ComponentType = NoopPage;
let EvalsPage: ComponentType = NoopPage;
let IngestionPage: ComponentType = NoopPage;
let DataSourcesPage: ComponentType = NoopPage;
let LogsPage: ComponentType = NoopPage;
let TelemetryPage: ComponentType = NoopPage;
let MonitoringPage: ComponentType = NoopPage;
let AlertsPage: ComponentType = NoopPage;
let SettingsPage: ComponentType = NoopPage;
let AdminsPage: ComponentType = NoopPage;
let FeedbackPage: ComponentType = NoopPage;
let OkfManagerPage: ComponentType = NoopPage;
let JobsPage: ComponentType = NoopPage;
let RAGFlowPage: ComponentType = NoopPage;
let AdminSelfCheckPage: ComponentType = NoopPage;
let CachePage: ComponentType = NoopPage;


if (ADMIN_ENABLED) {
  AdminLoginPage = lazyWithRetry(() => import("./admin/pages/AdminLoginPage"));
  AdminShell = lazyWithRetry(() => import("./admin/layout/AdminShell").then(m => ({ default: m.AdminShell })));
  OverviewPage = lazyWithRetry(() => import("./admin/pages/OverviewPage"));
  QueriesPage = lazyWithRetry(() => import("./admin/pages/QueriesPage"));
  QualityPage = lazyWithRetry(() => import("./admin/pages/QualityPage"));
  RetrievalPage = lazyWithRetry(() => import("./admin/pages/RetrievalPage"));
  DailyTeachingPage = lazyWithRetry(() => import("./admin/pages/DailyTeachingPage"));
  TeachingTipsPage = lazyWithRetry(() => import("./admin/pages/TeachingTipsPage"));
  TriggersPage = lazyWithRetry(() => import("./admin/pages/TriggersPage"));
  TopicsPage = lazyWithRetry(() => import("./admin/pages/TopicsPage"));
  PromptsPage = lazyWithRetry(() => import("./admin/pages/PromptsPage"));
  EvalsPage = lazyWithRetry(() => import("./admin/pages/EvalsPage"));
  IngestionPage = lazyWithRetry(() => import("./admin/pages/IngestionPage"));
  DataSourcesPage = lazyWithRetry(() => import("./admin/pages/DataSourcesPage"));
  LogsPage = lazyWithRetry(() => import("./admin/pages/LogsPage"));
  TelemetryPage = lazyWithRetry(() => import("./admin/pages/TelemetryPage"));
  MonitoringPage = lazyWithRetry(() => import("./admin/pages/MonitoringPage"));
  AlertsPage = lazyWithRetry(() => import("./admin/pages/AlertsPage"));
  SettingsPage = lazyWithRetry(() => import("./admin/pages/SettingsPage"));
  AdminsPage = lazyWithRetry(() => import("./admin/pages/AdminsPage"));
  FeedbackPage = lazyWithRetry(() => import("./admin/pages/FeedbackPage"));
  OkfManagerPage = lazyWithRetry(() => import("./admin/pages/OkfManager"));
  JobsPage = lazyWithRetry(() => import("./admin/pages/JobsPage"));
  RAGFlowPage = lazyWithRetry(() => import("./admin/pages/RAGFlowPage"));
  AdminSelfCheckPage = lazyWithRetry(() => import("./pages/AdminSelfCheckPage"));
  CachePage = lazyWithRetry(() => import("./admin/pages/CachePage"));
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: (failureCount, error) => {
        // Do not retry auth failures; retry everything else up to 2 times.
        if (error instanceof Response && error.status === 401) return false;
        if ((error as { status?: number })?.status === 401) return false;
        return failureCount < 3;
      },
      throwOnError: false,
    },
  },
});

/**
 * Query-aware error boundary. Catches errors thrown by query-bound components
 * (when throwOnError is enabled for a specific query) and TanStack Query's
 * propagated errors, showing a recoverable fallback instead of suspending forever.
 */
const QueryErrorBoundary = ({ children }: { children: React.ReactNode }) => (
  <ChatErrorBoundary>
    {children}
  </ChatErrorBoundary>
);

const DebugLayout = () => (
  <div id="debug-layout">
    <Outlet />
  </div>
);

const isNativePlatform = Capacitor.isNativePlatform();

// Wraps each lazy admin child route in its own Suspense (so one route's
// chunk-loading or render failure never suspends/crashes the whole admin
// area — P1-AI-19) plus the admin error boundary (per-page crash isolation).
const AdminRoute = ({ children }: { children: React.ReactNode }) => (
  <AdminErrorBoundary>
    <Suspense fallback={<BrandedSpinner />}>{children}</Suspense>
  </AdminErrorBoundary>
);

const AppRouter = ({ children }: { children: React.ReactNode }) => {
  const future = { v7_startTransition: true, v7_relativeSplatPath: true } as const;
  return isNativePlatform ? (
    <HashRouter future={future}>{children}</HashRouter>
  ) : (
    <BrowserRouter future={future}>{children}</BrowserRouter>
  );
};

const RouteTracker = () => {
  const location = useLocation();
  useEffect(() => {
    trackPageview(location.pathname);
  }, [location.pathname]);
  return null;
};

const App = () => {
  useEffect(() => {
    console.log('[App] Mounted');
    
    const runPurge = () => {
      purgeConversationsByAge(getRetentionDays()).catch((err) => {
        captureFeatureError(err, 'chat', { action: 'purgeConversationsByAge' });
      });
    };

    runPurge();

    const handleRetry = () => {
      runPurge();
    };

    window.addEventListener('retry-retention-purge', handleRetry);
    window.retryRetentionPurge = handleRetry;

    // Preload critical route chunks after initial render
    preloadCriticalRoutes();

    return () => {
      window.removeEventListener('retry-retention-purge', handleRetry);
      delete window.retryRetentionPurge;
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      {/*
        SereneMindProvider wraps the entire router so every route
        (ChatInterface, PrePracticeGate, AppShell, CommandPalette)
        can call useSereneMind() and get a real context, not the no-op fallback.
        Previously missing from this tree — Serene Mind modal never rendered.
      */}
      <SereneMindProvider>
        <QueryErrorBoundary>
        <AppRouter>
          <RouteTracker />
          <Routes>
            {/* Admin — only mounted when VITE_ADMIN_ENABLED !== 'false'.
                When disabled, Vite tree-shakes the imports above so no
                admin route paths or chunks reach the bundle. */}
            {ADMIN_ENABLED && (
              <>
                <Route path="/admin/login" element={
                  <Suspense fallback={<BrandedSpinner />}><AdminLoginPage /></Suspense>
                } />
                <Route path="/admin" element={
                  <Suspense fallback={<BrandedSpinner />}><AdminShell /></Suspense>
                }>
                  <Route index element={<AdminRoute><OverviewPage /></AdminRoute>} />
                  <Route path="queries" element={<AdminRoute><QueriesPage /></AdminRoute>} />
                  <Route path="quality" element={<AdminRoute><QualityPage /></AdminRoute>} />
                  <Route path="retrieval" element={<AdminRoute><RetrievalPage /></AdminRoute>} />
                  <Route path="daily-teaching" element={<AdminRoute><DailyTeachingPage /></AdminRoute>} />
                  <Route path="teaching-tips" element={<AdminRoute><TeachingTipsPage /></AdminRoute>} />
                  <Route path="triggers" element={<AdminRoute><TriggersPage /></AdminRoute>} />
                  <Route path="topics" element={<AdminRoute><TopicsPage /></AdminRoute>} />
                  <Route path="prompts" element={<AdminRoute><PromptsPage /></AdminRoute>} />
                  <Route path="evals" element={<AdminRoute><EvalsPage /></AdminRoute>} />
                  <Route path="queue" element={<AdminRoute><JobsPage /></AdminRoute>} />
                  <Route path="ingestion" element={<AdminRoute><IngestionPage /></AdminRoute>} />
                  <Route path="data-sources" element={<AdminRoute><DataSourcesPage /></AdminRoute>} />
                  <Route path="logs" element={<AdminRoute><LogsPage /></AdminRoute>} />
                  <Route path="telemetry" element={<AdminRoute><TelemetryPage /></AdminRoute>} />
                  <Route path="monitoring" element={<AdminRoute><MonitoringPage /></AdminRoute>} />
                  <Route path="alerts" element={<AdminRoute><AlertsPage /></AdminRoute>} />
                  <Route path="settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
                  <Route path="admins" element={<AdminRoute><AdminsPage /></AdminRoute>} />
                  <Route path="feedback" element={<AdminRoute><FeedbackPage /></AdminRoute>} />
                  <Route path="okf" element={<AdminRoute><OkfManagerPage /></AdminRoute>} />
                  <Route path="rag-flow" element={<AdminRoute><RAGFlowPage /></AdminRoute>} />
                  <Route path="cache" element={<AdminRoute><CachePage /></AdminRoute>} />
                  <Route path="self-check" element={<AdminRoute><AdminSelfCheckPage /></AdminRoute>} />
                </Route>
              </>
            )}

            {/* Seeker */}
            <Route element={<DebugLayout />}>
              <Route path="/" element={<Suspense fallback={<BrandedSpinner />}><Index /></Suspense>} />
              <Route path="/auth" element={<Suspense fallback={<BrandedSpinner />}><AuthPage /></Suspense>} />
              <Route path="/auth/mfa" element={<Suspense fallback={<BrandedSpinner />}><MFAChallengePage /></Suspense>} />
              {!import.meta.env.PROD && (
                <>
                  <Route path="/auth/diagnostics" element={<Suspense fallback={<BrandedSpinner />}><AuthDiagnosticsPage /></Suspense>} />
                  <Route path="/auth/latency" element={<Suspense fallback={<BrandedSpinner />}><AuthLatencyDashboard /></Suspense>} />
                  <Route path="/test-tts" element={<Suspense fallback={<BrandedSpinner />}><TTSVerificationPage /></Suspense>} />
                </>
              )}
              <Route path="/reset-password" element={<Suspense fallback={<BrandedSpinner />}><ResetPasswordPage /></Suspense>} />
              <Route path="/privacy" element={<Suspense fallback={<BrandedSpinner />}><PrivacyPage /></Suspense>} />
              <Route path="/terms" element={<Suspense fallback={<BrandedSpinner />}><TermsPage /></Suspense>} />
              <Route path="/chat" element={<Suspense fallback={<BrandedSpinner />}><ChatPage /></Suspense>} />
              <Route path="/profile" element={<Suspense fallback={<BrandedSpinner />}><ProfilePage /></Suspense>} />
              <Route path="/practices" element={<Suspense fallback={<BrandedSpinner />}><PracticesPage /></Suspense>} />
              <Route path="/practices/:slug" element={<Suspense fallback={<BrandedSpinner />}><PracticeDetailPage /></Suspense>} />
              <Route path="/guides/spirit-guides" element={<Suspense fallback={<BrandedSpinner />}><SpiritGuidesPage /></Suspense>} />
              <Route path="/guides/ai-spiritual-companion" element={<Suspense fallback={<BrandedSpinner />}><AiSpiritualCompanionPage /></Suspense>} />
              <Route path="/guides/beautiful-state-meditation" element={<Suspense fallback={<BrandedSpinner />}><BeautifulStateMeditationPage /></Suspense>} />
              <Route path="/guides/serene-mind-practice" element={<Suspense fallback={<BrandedSpinner />}><SereneMindPracticePage /></Suspense>} />
              <Route path="/guides/self-centric-thinking" element={<Suspense fallback={<BrandedSpinner />}><SelfCentricThinkingPage /></Suspense>} />
              <Route path="/guides/spiritual-guide-for-anxiety" element={<Suspense fallback={<BrandedSpinner />}><SpiritualGuideForAnxietyPage /></Suspense>} />
              <Route path="/guides/suffering-to-beautiful-state" element={<Suspense fallback={<BrandedSpinner />}><SufferingToBeautifulStatePage /></Suspense>} />
              <Route path="/notebooks" element={<Suspense fallback={<BrandedSpinner />}><StudyNotebookPage /></Suspense>} />
              <Route path="/knowledge-graph" element={<Suspense fallback={<BrandedSpinner />}><KnowledgeGraphPage /></Suspense>} />
              <Route path="/second-brain" element={<Suspense fallback={<BrandedSpinner />}><SecondBrainPage /></Suspense>} />
              <Route path="*" element={<Suspense fallback={<BrandedSpinner />}><NotFound /></Suspense>} />
            </Route>
          </Routes>
          <SessionExpiredHandler />
          <CookieConsentBanner />
          <PushPermissionPrompt />
          <PushNotificationsManager />
          <SonnerToaster />
          <Toaster />


        </AppRouter>
        </QueryErrorBoundary>
      </SereneMindProvider>
    </QueryClientProvider>
  );
};

export default App;
