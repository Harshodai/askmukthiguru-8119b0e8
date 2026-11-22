import { useEffect, Suspense, type ComponentType, type ReactNode } from "react";
import { lazyWithRetry, preloadCriticalRoutes } from "@/lib/lazyWithRetry";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { installReducedMotionGuard } from "@/lib/reducedMotionGuard";
import { BrowserRouter, HashRouter, Routes, Route, Outlet, Navigate, useLocation } from "react-router-dom";
import { GroupedPage } from "@/admin/pages/GroupedPage";
import { Capacitor } from "@capacitor/core";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { SessionExpiredHandler } from "@/components/common/SessionExpiredHandler";
import { FacultyAccessGate } from "@/components/common/FacultyAccessGate";
import { CookieConsentBanner } from "@/components/common/CookieConsentBanner";
import { SafetyDisclaimer } from "@/components/common/SafetyDisclaimer";
import { BrandedSpinner } from "@/components/common/BrandedSpinner";
import { AdminErrorBoundary } from "@/admin/components/AdminErrorBoundary";
import { ChatErrorBoundary } from "@/components/common/ChatErrorBoundary";
import { SereneMindProvider } from "@/components/common/SereneMindProvider";
import { ThemeProvider } from "@/components/common/ThemeProvider";
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
const AgeConfirmPage = lazyWithRetry(() => import("./pages/AgeConfirmPage"));
const MFAChallengePage = lazyWithRetry(() => import("./pages/MFAChallengePage"));
const AuthDiagnosticsPage = lazyWithRetry(() => import("./pages/AuthDiagnosticsPage"));
const AuthLatencyDashboard = lazyWithRetry(() => import("./pages/AuthLatencyDashboard"));
const ResetPasswordPage = lazyWithRetry(() => import("./pages/ResetPasswordPage"));
const PrivacyPage = lazyWithRetry(() => import("./pages/PrivacyPage"));
const TrustPage = lazyWithRetry(() => import("./pages/TrustPage"));
const TermsPage = lazyWithRetry(() => import("./pages/TermsPage"));
const UnsubscribePage = lazyWithRetry(() => import("./pages/UnsubscribePage"));
const TTSVerificationPage = lazyWithRetry(() => import("./pages/TTSVerificationPage"));
const AiSpiritualCompanionPage = lazyWithRetry(() => import("./pages/guides/AiSpiritualCompanionPage"));
const BeautifulStateMeditationPage = lazyWithRetry(() => import("./pages/guides/BeautifulStateMeditationPage"));
const SereneMindPracticePage = lazyWithRetry(() => import("./pages/guides/SereneMindPracticePage"));
const SelfCentricThinkingPage = lazyWithRetry(() => import("./pages/guides/SelfCentricThinkingPage"));
const SpiritualGuideForAnxietyPage = lazyWithRetry(() => import("./pages/guides/SpiritualGuideForAnxietyPage"));
const SufferingToBeautifulStatePage = lazyWithRetry(() => import("./pages/guides/SufferingToBeautifulStatePage"));
const StudyNotebookPage = lazyWithRetry(() => import("./pages/StudyNotebookPage"));
const KnowledgeGraphPage = lazyWithRetry(() => import("./pages/KnowledgeGraphPage"));
const SecondBrainPage = lazyWithRetry(() => import("./pages/SecondBrainPage"));
const LinkWhatsAppPage = lazyWithRetry(() => import("./pages/LinkWhatsAppPage"));

// First-person verbatim teaching route — isolated behind its own flag so it
// can ship independently of the rest of the app. Vite tree-shakes the import
// (and route) out of the bundle entirely when the flag is 'false'/unset.
const FIRST_PERSON_ENABLED = import.meta.env.VITE_FIRST_PERSON_ENABLED === 'true';
const TeacherWordsPage = FIRST_PERSON_ENABLED
  ? lazyWithRetry(() => import("./pages/TeacherWords"))
  : (() => null);

// Admin — hidden at runtime when VITE_ADMIN_ENABLED='false' (default false;
// .env.example). Routes below are not mounted and AdminShell redirects to
// login, but the admin chunks stay in the bundle — this flag is a runtime
// gate, not a tree-shaking boundary. Vite replaces
// import.meta.env.VITE_ADMIN_ENABLED at build time.
const ADMIN_ENABLED = import.meta.env.VITE_ADMIN_ENABLED !== 'false';
// Diagnostics remain absent from ordinary production builds; Playwright may
// opt into the standalone verification page with an explicit test-only flag.
const DIAGNOSTICS_ENABLED =
  !import.meta.env.PROD || import.meta.env.VITE_ENABLE_E2E_DIAGNOSTICS === 'true';
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
let EventsPage: ComponentType = NoopPage;
let TeachingTipsPage: ComponentType = NoopPage;
let TriggersPage: ComponentType = NoopPage;
let TopicsPage: ComponentType = NoopPage;
let PromptsPage: ComponentType = NoopPage;
let EvalsPage: ComponentType = NoopPage;
let IngestionWorkflowPage: ComponentType = NoopPage;
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
let RoutingPage: ComponentType = NoopPage;
let ClipReportsPage: ComponentType = NoopPage;
let SpeakerAttributionPage: ComponentType = NoopPage;
let VideoApprovalPage: ComponentType = NoopPage;
let ObservabilityDashboard: ComponentType = NoopPage;
let WaitlistSubscribersPage: ComponentType = NoopPage;
let HumanReviewGatesPage: ComponentType = NoopPage;


if (ADMIN_ENABLED) {
  AdminLoginPage = lazyWithRetry(() => import("./admin/pages/AdminLoginPage"));
  AdminShell = lazyWithRetry(() => import("./admin/layout/AdminShell").then(m => ({ default: m.AdminShell })));
  OverviewPage = lazyWithRetry(() => import("./admin/pages/OverviewPage"));
  QueriesPage = lazyWithRetry(() => import("./admin/pages/QueriesPage"));
  QualityPage = lazyWithRetry(() => import("./admin/pages/QualityPage"));
  RetrievalPage = lazyWithRetry(() => import("./admin/pages/RetrievalPage"));
  DailyTeachingPage = lazyWithRetry(() => import("./admin/pages/DailyTeachingPage"));
  EventsPage = lazyWithRetry(() => import("./admin/pages/EventsPage"));
  TeachingTipsPage = lazyWithRetry(() => import("./admin/pages/TeachingTipsPage"));
  TriggersPage = lazyWithRetry(() => import("./admin/pages/TriggersPage"));
  TopicsPage = lazyWithRetry(() => import("./admin/pages/TopicsPage"));
  PromptsPage = lazyWithRetry(() => import("./admin/pages/PromptsPage"));
  EvalsPage = lazyWithRetry(() => import("./admin/pages/EvalsPage"));
  IngestionWorkflowPage = lazyWithRetry(() => import("./admin/pages/IngestionWorkflowPage"));
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
  RoutingPage = lazyWithRetry(() => import("./admin/pages/RoutingPage"));
  ClipReportsPage = lazyWithRetry(() => import("./admin/pages/ClipReportsPage"));
  WaitlistSubscribersPage = lazyWithRetry(() => import("./admin/pages/WaitlistSubscribersPage"));
  SpeakerAttributionPage = lazyWithRetry(() => import("./admin/pages/SpeakerAttributionPage"));
  VideoApprovalPage = lazyWithRetry(() => import("./admin/pages/VideoApprovalPage"));
  ObservabilityDashboard = lazyWithRetry(() => import("./admin/components/ObservabilityDashboard").then(m => ({ default: m.ObservabilityDashboard })));
  HumanReviewGatesPage = lazyWithRetry(() => import("./admin/pages/HumanReviewGatesPage"));
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
  <div id="debug-layout" className="h-full w-full">
    <main id="main-content" tabIndex={-1} className="h-full w-full">
      <Outlet />
    </main>
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
  return isNativePlatform ? (
    <HashRouter>{children}</HashRouter>
  ) : (
    <BrowserRouter>{children}</BrowserRouter>
  );
};

const RouteTracker = () => {
  const location = useLocation();
  useEffect(() => {
    trackPageview(location.pathname);
  }, [location.pathname]);
  return null;
};

/** New page = top of the page. A #hash link scrolls to its target instead. */
const ScrollToTop = () => {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      document.getElementById(hash.slice(1))?.scrollIntoView();
      return;
    }
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.getElementById('main-content')?.scrollTo?.({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname, hash]);
  return null;
};

const App = () => {
  useEffect(() => {
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

    // NEW-A11Y-8 (A11Y-12): stop looping decorative animation under "reduce motion".
    const stopMotionGuard = installReducedMotionGuard();

    return () => {
      stopMotionGuard();
      window.removeEventListener('retry-retention-purge', handleRetry);
      delete window.retryRetentionPurge;
    };
  }, []);

  return (
    <FacultyAccessGate>
    <MotionConfig reducedMotion="user">
    <QueryClientProvider client={queryClient}>
      {/*
        SereneMindProvider wraps the entire router so every route
        (ChatInterface, PrePracticeGate, AppShell, CommandPalette)
        can call useSereneMind() and get a real context, not the no-op fallback.
        Previously missing from this tree — Serene Mind modal never rendered.
      */}
      <ThemeProvider>
      <SereneMindProvider>
        <QueryErrorBoundary>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[9999] focus:bg-white focus:px-4 focus:py-2 focus:rounded-lg focus:shadow-lg focus:text-slate-900"
        >
          Skip to main content
        </a>
        <AppRouter>
          <RouteTracker />
          <ScrollToTop />
          <Routes>
            {/* Admin — only mounted when VITE_ADMIN_ENABLED !== 'false'.
                When disabled the routes stay unmounted (runtime gate); admin
                chunks remain in the bundle. */}
            {ADMIN_ENABLED && (
              <>
                <Route path="/admin/login" element={
                  <Suspense fallback={<BrandedSpinner />}><AdminLoginPage /></Suspense>
                } />
                <Route path="/admin" element={
                  <Suspense fallback={<BrandedSpinner />}><AdminShell /></Suspense>
                }>
                  <Route index element={<AdminRoute><OverviewPage /></AdminRoute>} />

                  {/* Query Insights: queries · retrieval · quality · clip reports */}
                  <Route path="queries" element={<AdminRoute><GroupedPage tabs={[
                    { id: 'queries', label: 'Queries', Component: QueriesPage },
                    { id: 'retrieval', label: 'Retrieval', Component: RetrievalPage },
                    { id: 'quality', label: 'Quality', Component: QualityPage },
                    { id: 'clip-reports', label: 'Clip Reports', Component: ClipReportsPage },
                  ]} /></AdminRoute>} />
                  <Route path="retrieval" element={<Navigate to="/admin/queries?tab=retrieval" replace />} />
                  <Route path="quality" element={<Navigate to="/admin/queries?tab=quality" replace />} />

                  {/* Content CMS: teachings · tips · topics · OKF */}
                  <Route path="content" element={<AdminRoute><GroupedPage tabs={[
                    { id: 'daily-teaching', label: 'Daily Teaching', Component: DailyTeachingPage },
                    { id: 'events', label: 'Events', Component: EventsPage },
                    { id: 'teaching-tips', label: 'Teaching Tips', Component: TeachingTipsPage },
                    { id: 'topics', label: 'Topics', Component: TopicsPage },
                    { id: 'okf', label: 'OKF', Component: OkfManagerPage },
                  ]} /></AdminRoute>} />
                  <Route path="daily-teaching" element={<Navigate to="/admin/content" replace />} />
                  <Route path="teaching-tips" element={<Navigate to="/admin/content?tab=teaching-tips" replace />} />
                  <Route path="topics" element={<Navigate to="/admin/content?tab=topics" replace />} />
                  <Route path="okf" element={<Navigate to="/admin/content?tab=okf" replace />} />

                  {/* Evaluation: evals · prompts · human-gates */}
                  <Route path="evals" element={<AdminRoute><GroupedPage tabs={[
                    { id: 'evals', label: 'Eval Runs', Component: EvalsPage },
                    { id: 'prompts', label: 'Prompts', Component: PromptsPage },
                    { id: 'human-gates', label: 'Human Review Gates', Component: HumanReviewGatesPage },
                  ]} /></AdminRoute>} />
                  <Route path="prompts" element={<Navigate to="/admin/evals?tab=prompts" replace />} />
                  <Route path="human-gates" element={<Navigate to="/admin/evals?tab=human-gates" replace />} />

                  {/* Reliability: alerts · triggers */}
                  <Route path="alerts" element={<AdminRoute><GroupedPage tabs={[
                    { id: 'alerts', label: 'Alerts', Component: AlertsPage },
                    { id: 'triggers', label: 'Triggers', Component: TriggersPage },
                  ]} /></AdminRoute>} />
                  <Route path="triggers" element={<Navigate to="/admin/alerts?tab=triggers" replace />} />

                  {/* Ingestion ops: workflow · pipeline · attribution · video approval · queue · cache */}
                  <Route path="ingestion" element={<AdminRoute><GroupedPage tabs={[
                    { id: 'workflow', label: 'Workflow DAG', Component: IngestionWorkflowPage },
                    { id: 'ingestion', label: 'Pipeline', Component: IngestionPage },
                    { id: 'attribution', label: 'Speaker & Dialogue', Component: SpeakerAttributionPage },
                    { id: 'video-approval', label: 'Video Approval', Component: VideoApprovalPage },
                    { id: 'queue', label: 'Queue', Component: JobsPage },
                    { id: 'cache', label: 'Cache', Component: CachePage },
                  ]} /></AdminRoute>} />
                  <Route path="workflow" element={<Navigate to="/admin/ingestion?tab=workflow" replace />} />
                  <Route path="attribution" element={<Navigate to="/admin/ingestion?tab=attribution" replace />} />
                  <Route path="video-approval" element={<Navigate to="/admin/ingestion?tab=video-approval" replace />} />
                  <Route path="queue" element={<Navigate to="/admin/ingestion?tab=queue" replace />} />
                  <Route path="cache" element={<Navigate to="/admin/ingestion?tab=cache" replace />} />

                  {/* Observability: overview · telemetry · logs · monitoring */}
                  <Route path="telemetry" element={<AdminRoute><GroupedPage tabs={[
                    { id: 'overview', label: 'Overview', Component: ObservabilityDashboard },
                    { id: 'telemetry', label: 'Telemetry', Component: TelemetryPage },
                    { id: 'logs', label: 'Logs', Component: LogsPage },
                    { id: 'monitoring', label: 'Monitoring', Component: MonitoringPage },
                  ]} /></AdminRoute>} />
                  <Route path="logs" element={<Navigate to="/admin/telemetry?tab=logs" replace />} />
                  <Route path="monitoring" element={<Navigate to="/admin/telemetry?tab=monitoring" replace />} />

                  <Route path="routing" element={<AdminRoute><RoutingPage /></AdminRoute>} />

                  <Route path="data-sources" element={<AdminRoute><DataSourcesPage /></AdminRoute>} />
                  <Route path="rag-flow" element={<AdminRoute><RAGFlowPage /></AdminRoute>} />
                  <Route path="feedback" element={<AdminRoute><FeedbackPage /></AdminRoute>} />
                  <Route path="subscribers" element={<AdminRoute><WaitlistSubscribersPage /></AdminRoute>} />
                  <Route path="settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
                  <Route path="admins" element={<AdminRoute><AdminsPage /></AdminRoute>} />
                  <Route path="self-check" element={<AdminRoute><AdminSelfCheckPage /></AdminRoute>} />

                </Route>
              </>
            )}

            {/* Seeker */}
            <Route element={<DebugLayout />}>
              <Route path="/" element={<Suspense fallback={<BrandedSpinner />}><Index /></Suspense>} />
              <Route path="/auth" element={<Suspense fallback={<BrandedSpinner />}><AuthPage /></Suspense>} />
              <Route path="/auth/confirm-age" element={<Suspense fallback={<BrandedSpinner />}><AgeConfirmPage /></Suspense>} />
              <Route path="/auth/mfa" element={<Suspense fallback={<BrandedSpinner />}><MFAChallengePage /></Suspense>} />
              {DIAGNOSTICS_ENABLED && (
                <>
                  <Route path="/auth/diagnostics" element={<Suspense fallback={<BrandedSpinner />}><AuthDiagnosticsPage /></Suspense>} />
                  <Route path="/auth/latency" element={<Suspense fallback={<BrandedSpinner />}><AuthLatencyDashboard /></Suspense>} />
                  <Route path="/test-tts" element={<Suspense fallback={<BrandedSpinner />}><TTSVerificationPage /></Suspense>} />
                </>
              )}
              <Route path="/reset-password" element={<Suspense fallback={<BrandedSpinner />}><ResetPasswordPage /></Suspense>} />
              <Route path="/privacy" element={<Suspense fallback={<BrandedSpinner />}><PrivacyPage /></Suspense>} />
              <Route path="/trust" element={<Suspense fallback={<BrandedSpinner />}><TrustPage /></Suspense>} />
              <Route path="/terms" element={<Suspense fallback={<BrandedSpinner />}><TermsPage /></Suspense>} />
              <Route path="/unsubscribe" element={<Suspense fallback={<BrandedSpinner />}><UnsubscribePage /></Suspense>} />
              <Route path="/chat" element={<Suspense fallback={<BrandedSpinner />}><ChatPage /></Suspense>} />
              <Route path="/profile" element={<Suspense fallback={<BrandedSpinner />}><ProfilePage /></Suspense>} />
              <Route path="/practices" element={<Suspense fallback={<BrandedSpinner />}><PracticesPage /></Suspense>} />
              <Route path="/practices/:slug" element={<Suspense fallback={<BrandedSpinner />}><PracticeDetailPage /></Suspense>} />
              <Route path="/link-whatsapp" element={<Suspense fallback={<BrandedSpinner />}><LinkWhatsAppPage /></Suspense>} />
              {/* Compatibility entry points: keep shared public links from becoming hard 404s. */}
              <Route path="/guides" element={<Navigate to="/guides/ai-spiritual-companion" replace />} />
              <Route path="/support" element={<Navigate to="/profile?tab=settings" replace />} />
              {/* Quarantined until an owner-approved, source-backed content register exists. */}
              <Route path="/guides/spirit-guides" element={<Navigate to="/guides/ai-spiritual-companion" replace />} />
              <Route path="/guides/ai-spiritual-companion" element={<Suspense fallback={<BrandedSpinner />}><AiSpiritualCompanionPage /></Suspense>} />
              <Route path="/guides/beautiful-state-meditation" element={<Suspense fallback={<BrandedSpinner />}><BeautifulStateMeditationPage /></Suspense>} />
              <Route path="/guides/serene-mind-practice" element={<Suspense fallback={<BrandedSpinner />}><SereneMindPracticePage /></Suspense>} />
              <Route path="/guides/self-centric-thinking" element={<Suspense fallback={<BrandedSpinner />}><SelfCentricThinkingPage /></Suspense>} />
              <Route path="/guides/spiritual-guide-for-anxiety" element={<Suspense fallback={<BrandedSpinner />}><SpiritualGuideForAnxietyPage /></Suspense>} />
              <Route path="/guides/suffering-to-beautiful-state" element={<Suspense fallback={<BrandedSpinner />}><SufferingToBeautifulStatePage /></Suspense>} />
              <Route path="/notebooks" element={<Suspense fallback={<BrandedSpinner />}><StudyNotebookPage /></Suspense>} />
              <Route path="/knowledge-graph" element={<Suspense fallback={<BrandedSpinner />}><KnowledgeGraphPage /></Suspense>} />
              <Route path="/wisdom-map" element={<Navigate to="/knowledge-graph" replace />} />
              <Route path="/second-brain" element={<Suspense fallback={<BrandedSpinner />}><SecondBrainPage /></Suspense>} />
              <Route path="/reflections" element={<Navigate to="/second-brain" replace />} />
              {FIRST_PERSON_ENABLED && (
                <Route path="/teachers-words" element={<Suspense fallback={<BrandedSpinner />}><TeacherWordsPage /></Suspense>} />
              )}
              <Route path="*" element={<Suspense fallback={<BrandedSpinner />}><NotFound /></Suspense>} />
            </Route>
          </Routes>
          <SessionExpiredHandler />
          <SafetyDisclaimer />
          <CookieConsentBanner />
          <PushPermissionPrompt />
          <PushNotificationsManager />
          <SonnerToaster />
          <Toaster />


        </AppRouter>
        </QueryErrorBoundary>
      </SereneMindProvider>
      </ThemeProvider>
    </QueryClientProvider>
    </MotionConfig>
    </FacultyAccessGate>
  );
};

export default App;
