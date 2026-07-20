import { useEffect, Suspense } from "react";
import { lazyWithRetry, preloadCriticalRoutes } from "@/lib/lazyWithRetry";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, HashRouter, Routes, Route, Outlet, useLocation } from "react-router-dom";
import { Capacitor } from "@capacitor/core";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { SessionExpiredHandler } from "@/components/common/SessionExpiredHandler";
import { CookieConsentBanner } from "@/components/common/CookieConsentBanner";
import { BrandedSpinner } from "@/components/common/BrandedSpinner";
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

let AdminLoginPage: any = null;
let AdminShell: any = null;
let OverviewPage: any = null;
let QueriesPage: any = null;
let QualityPage: any = null;
let RetrievalPage: any = null;
let DailyTeachingPage: any = null;
let TeachingTipsPage: any = null;
let TriggersPage: any = null;
let TopicsPage: any = null;
let PromptsPage: any = null;
let EvalsPage: any = null;
let IngestionPage: any = null;
let DataSourcesPage: any = null;
let LogsPage: any = null;
let TelemetryPage: any = null;
let MonitoringPage: any = null;
let AlertsPage: any = null;
let SettingsPage: any = null;
let AdminsPage: any = null;
let FeedbackPage: any = null;
let OkfManagerPage: any = null;
let JobsPage: any = null;
let RAGFlowPage: any = null;
let AdminSelfCheckPage: any = null;
let CachePage: any = null;


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

const queryClient = new QueryClient();

const DebugLayout = () => (
  <div id="debug-layout">
    <Outlet />
  </div>
);

const isNativePlatform = Capacitor.isNativePlatform();

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
    (window as any).retryRetentionPurge = handleRetry;

    // Preload critical route chunks after initial render
    preloadCriticalRoutes();

    return () => {
      window.removeEventListener('retry-retention-purge', handleRetry);
      delete (window as any).retryRetentionPurge;
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
                  <Route index element={<OverviewPage />} />
                  <Route path="queries" element={<QueriesPage />} />
                  <Route path="quality" element={<QualityPage />} />
                  <Route path="retrieval" element={<RetrievalPage />} />
                  <Route path="daily-teaching" element={<DailyTeachingPage />} />
                  <Route path="teaching-tips" element={<TeachingTipsPage />} />
                  <Route path="triggers" element={<TriggersPage />} />
                  <Route path="topics" element={<TopicsPage />} />
                  <Route path="prompts" element={<PromptsPage />} />
                  <Route path="evals" element={<EvalsPage />} />
                  <Route path="queue" element={<JobsPage />} />
                  <Route path="ingestion" element={<IngestionPage />} />
                  <Route path="data-sources" element={<DataSourcesPage />} />
                  <Route path="logs" element={<LogsPage />} />
                  <Route path="telemetry" element={<TelemetryPage />} />
                  <Route path="monitoring" element={<MonitoringPage />} />
                  <Route path="alerts" element={<AlertsPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="admins" element={<AdminsPage />} />
                  <Route path="feedback" element={<FeedbackPage />} />
                  <Route path="okf" element={<OkfManagerPage />} />
                  <Route path="rag-flow" element={
                    <Suspense fallback={<BrandedSpinner />}><RAGFlowPage /></Suspense>
                  } />
                  <Route path="cache" element={<CachePage />} />
                  <Route path="self-check" element={
                    <Suspense fallback={<BrandedSpinner />}><AdminSelfCheckPage /></Suspense>
                  } />
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
      </SereneMindProvider>
    </QueryClientProvider>
  );
};

export default App;
