import { useEffect, lazy, Suspense } from "react";
import { supabase } from "@/integrations/supabase/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { SessionExpiredHandler } from "@/components/common/SessionExpiredHandler";
import { CookieConsentBanner } from "@/components/common/CookieConsentBanner";

// Pages
const Index = lazy(() => import("./pages/Index"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const PracticesPage = lazy(() => import("./pages/PracticesPage"));
const PracticeDetailPage = lazy(() => import("./pages/PracticeDetailPage"));
const NotFound = lazy(() => import("./pages/NotFound"));
const AuthPage = lazy(() => import("./pages/AuthPage"));
const AuthDiagnosticsPage = lazy(() => import("./pages/AuthDiagnosticsPage"));
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage"));
const TermsPage = lazy(() => import("./pages/TermsPage"));

// Admin
const AdminLoginPage = lazy(() => import("./admin/pages/AdminLoginPage"));
const AdminShell = lazy(() => import("./admin/layout/AdminShell").then(m => ({ default: m.AdminShell })));
const OverviewPage = lazy(() => import("./admin/pages/OverviewPage"));
const QueriesPage = lazy(() => import("./admin/pages/QueriesPage"));
const QualityPage = lazy(() => import("./admin/pages/QualityPage"));
const RetrievalPage = lazy(() => import("./admin/pages/RetrievalPage"));
const DailyTeachingPage = lazy(() => import("./admin/pages/DailyTeachingPage"));
const TriggersPage = lazy(() => import("./admin/pages/TriggersPage"));
const TopicsPage = lazy(() => import("./admin/pages/TopicsPage"));
const PromptsPage = lazy(() => import("./admin/pages/PromptsPage"));
const EvalsPage = lazy(() => import("./admin/pages/EvalsPage"));
const IngestionPage = lazy(() => import("./admin/pages/IngestionPage"));
const LogsPage = lazy(() => import("./admin/pages/LogsPage"));
const TelemetryPage = lazy(() => import("./admin/pages/TelemetryPage"));
const AlertsPage = lazy(() => import("./admin/pages/AlertsPage"));
const SettingsPage = lazy(() => import("./admin/pages/SettingsPage"));
const AdminsPage = lazy(() => import("./admin/pages/AdminsPage"));

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
      <BrowserRouter>
        <Routes>
          {/* Admin */}
          <Route path="/admin/login" element={
            <Suspense fallback={<div>Loading...</div>}><AdminLoginPage /></Suspense>
          } />
          <Route path="/admin" element={
            <Suspense fallback={<div>Loading...</div>}><AdminShell /></Suspense>
          }>
            <Route index element={<OverviewPage />} />
            <Route path="queries" element={<QueriesPage />} />
            <Route path="quality" element={<QualityPage />} />
            <Route path="retrieval" element={<RetrievalPage />} />
            <Route path="daily-teaching" element={<DailyTeachingPage />} />
            <Route path="triggers" element={<TriggersPage />} />
            <Route path="topics" element={<TopicsPage />} />
            <Route path="prompts" element={<PromptsPage />} />
            <Route path="evals" element={<EvalsPage />} />
            <Route path="ingestion" element={<IngestionPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="telemetry" element={<TelemetryPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="admins" element={<AdminsPage />} />
          </Route>

          {/* Seeker */}
          <Route element={<DebugLayout />}>
            <Route path="/" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><Index /></Suspense>} />
            <Route path="/auth" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><AuthPage /></Suspense>} />
            <Route path="/auth/diagnostics" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><AuthDiagnosticsPage /></Suspense>} />
            <Route path="/reset-password" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><ResetPasswordPage /></Suspense>} />
            <Route path="/privacy" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><PrivacyPage /></Suspense>} />
            <Route path="/terms" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><TermsPage /></Suspense>} />
            <Route path="/chat" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><ChatPage /></Suspense>} />
            <Route path="/profile" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><ProfilePage /></Suspense>} />
            <Route path="/practices" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><PracticesPage /></Suspense>} />
            <Route path="/practices/:slug" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><PracticeDetailPage /></Suspense>} />
            <Route path="*" element={<Suspense fallback={<div className="h-screen w-full flex items-center justify-center">Loading...</div>}><NotFound /></Suspense>} />
          </Route>
        </Routes>
        <SessionExpiredHandler />
        <CookieConsentBanner />
        <SonnerToaster richColors closeButton position="top-right" />
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
