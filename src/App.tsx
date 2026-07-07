import { useEffect, Suspense } from "react";
import { lazyWithRetry } from "@/lib/lazyWithRetry";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { SessionExpiredHandler } from "@/components/common/SessionExpiredHandler";
import { CookieConsentBanner } from "@/components/common/CookieConsentBanner";
import { BrandedSpinner } from "@/components/common/BrandedSpinner";
import { SereneMindProvider } from "@/components/common/SereneMindProvider";
import { PushPermissionPrompt } from "@/components/common/PushPermissionPrompt";

// Pages
const Index = lazyWithRetry(() => import("./pages/Index"));
const ChatPage = lazyWithRetry(() => import("./pages/ChatPage"));
const ProfilePage = lazyWithRetry(() => import("./pages/ProfilePage"));
const PracticesPage = lazyWithRetry(() => import("./pages/PracticesPage"));
const PracticeDetailPage = lazyWithRetry(() => import("./pages/PracticeDetailPage"));
const NotFound = lazyWithRetry(() => import("./pages/NotFound"));
const AuthPage = lazyWithRetry(() => import("./pages/AuthPage"));
const AuthDiagnosticsPage = lazyWithRetry(() => import("./pages/AuthDiagnosticsPage"));
const AuthLatencyDashboard = lazyWithRetry(() => import("./pages/AuthLatencyDashboard"));
const ResetPasswordPage = lazyWithRetry(() => import("./pages/ResetPasswordPage"));
const PrivacyPage = lazyWithRetry(() => import("./pages/PrivacyPage"));
const TermsPage = lazyWithRetry(() => import("./pages/TermsPage"));
const TTSVerificationPage = lazyWithRetry(() => import("./pages/TTSVerificationPage"));
const SpiritGuidesPage = lazyWithRetry(() => import("./pages/guides/SpiritGuidesPage"));
const StudyNotebookPage = lazyWithRetry(() => import("./pages/StudyNotebookPage"));
const KnowledgeGraphPage = lazyWithRetry(() => import("./pages/KnowledgeGraphPage"));

// Admin
const AdminLoginPage = lazyWithRetry(() => import("./admin/pages/AdminLoginPage"));
const AdminShell = lazyWithRetry(() => import("./admin/layout/AdminShell").then(m => ({ default: m.AdminShell })));
const OverviewPage = lazyWithRetry(() => import("./admin/pages/OverviewPage"));
const QueriesPage = lazyWithRetry(() => import("./admin/pages/QueriesPage"));
const QualityPage = lazyWithRetry(() => import("./admin/pages/QualityPage"));
const RetrievalPage = lazyWithRetry(() => import("./admin/pages/RetrievalPage"));
const DailyTeachingPage = lazyWithRetry(() => import("./admin/pages/DailyTeachingPage"));
const TeachingTipsPage = lazyWithRetry(() => import("./admin/pages/TeachingTipsPage"));
const TriggersPage = lazyWithRetry(() => import("./admin/pages/TriggersPage"));
const TopicsPage = lazyWithRetry(() => import("./admin/pages/TopicsPage"));
const PromptsPage = lazyWithRetry(() => import("./admin/pages/PromptsPage"));
const EvalsPage = lazyWithRetry(() => import("./admin/pages/EvalsPage"));
const IngestionPage = lazyWithRetry(() => import("./admin/pages/IngestionPage"));
const LogsPage = lazyWithRetry(() => import("./admin/pages/LogsPage"));
const TelemetryPage = lazyWithRetry(() => import("./admin/pages/TelemetryPage"));
const MonitoringPage = lazyWithRetry(() => import("./admin/pages/MonitoringPage"));
const AlertsPage = lazyWithRetry(() => import("./admin/pages/AlertsPage"));
const SettingsPage = lazyWithRetry(() => import("./admin/pages/SettingsPage"));
const AdminsPage = lazyWithRetry(() => import("./admin/pages/AdminsPage"));
const FeedbackPage = lazyWithRetry(() => import("./admin/pages/FeedbackPage"));
const OkfManagerPage = lazyWithRetry(() => import("./admin/pages/OkfManager"));
const JobsPage = lazyWithRetry(() => import("./admin/pages/JobsPage"));
const RAGFlowPage = lazyWithRetry(() => import("./admin/pages/RAGFlowPage"));

const queryClient = new QueryClient();

const DebugLayout = () => (
  <div id="debug-layout">
    <Outlet />
  </div>
);

const App = () => {
  useEffect(() => {
    console.log('[App] Mounted');
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
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            {/* Admin */}
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
            </Route>

            {/* Seeker */}
            <Route element={<DebugLayout />}>
              <Route path="/" element={<Suspense fallback={<BrandedSpinner />}><Index /></Suspense>} />
              <Route path="/auth" element={<Suspense fallback={<BrandedSpinner />}><AuthPage /></Suspense>} />
              <Route path="/auth/diagnostics" element={<Suspense fallback={<BrandedSpinner />}><AuthDiagnosticsPage /></Suspense>} />
              <Route path="/auth/latency" element={<Suspense fallback={<BrandedSpinner />}><AuthLatencyDashboard /></Suspense>} />
              <Route path="/reset-password" element={<Suspense fallback={<BrandedSpinner />}><ResetPasswordPage /></Suspense>} />
              <Route path="/privacy" element={<Suspense fallback={<BrandedSpinner />}><PrivacyPage /></Suspense>} />
              <Route path="/terms" element={<Suspense fallback={<BrandedSpinner />}><TermsPage /></Suspense>} />
              <Route path="/chat" element={<Suspense fallback={<BrandedSpinner />}><ChatPage /></Suspense>} />
              <Route path="/test-tts" element={<Suspense fallback={<BrandedSpinner />}><TTSVerificationPage /></Suspense>} />
              <Route path="/profile" element={<Suspense fallback={<BrandedSpinner />}><ProfilePage /></Suspense>} />
              <Route path="/practices" element={<Suspense fallback={<BrandedSpinner />}><PracticesPage /></Suspense>} />
              <Route path="/practices/:slug" element={<Suspense fallback={<BrandedSpinner />}><PracticeDetailPage /></Suspense>} />
              <Route path="/guides/spirit-guides" element={<Suspense fallback={<BrandedSpinner />}><SpiritGuidesPage /></Suspense>} />
              <Route path="/notebooks" element={<Suspense fallback={<BrandedSpinner />}><StudyNotebookPage /></Suspense>} />
              <Route path="/knowledge-graph" element={<Suspense fallback={<BrandedSpinner />}><KnowledgeGraphPage /></Suspense>} />
              <Route path="*" element={<Suspense fallback={<BrandedSpinner />}><NotFound /></Suspense>} />
            </Route>
          </Routes>
          <SessionExpiredHandler />
          <CookieConsentBanner />
          <PushPermissionPrompt />
          <SonnerToaster richColors closeButton position="top-right" />
          <Toaster />

        </BrowserRouter>
      </SereneMindProvider>
    </QueryClientProvider>
  );
};

export default App;
