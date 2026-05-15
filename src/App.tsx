import { useEffect, lazy, Suspense } from "react";
import { supabase } from "@/integrations/supabase/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { SessionExpiredHandler } from "@/components/common/SessionExpiredHandler";
import { CookieConsentBanner } from "@/components/common/CookieConsentBanner";

// Pages
import Index from "./pages/Index";
import ChatPage from "./pages/ChatPage";
import ProfilePage from "./pages/ProfilePage";
import PracticesPage from "./pages/PracticesPage";
import PracticeDetailPage from "./pages/PracticeDetailPage";
import NotFound from "./pages/NotFound";
import AuthPage from "./pages/AuthPage";
import AuthDiagnosticsPage from "./pages/AuthDiagnosticsPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import PrivacyPage from "./pages/PrivacyPage";
import TermsPage from "./pages/TermsPage";

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
            <Route path="/" element={<Index />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route path="/auth/diagnostics" element={<AuthDiagnosticsPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/practices" element={<PracticesPage />} />
            <Route path="/practices/:slug" element={<PracticeDetailPage />} />
            <Route path="*" element={<NotFound />} />
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
