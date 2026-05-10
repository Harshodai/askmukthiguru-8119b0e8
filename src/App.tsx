import { useEffect, lazy, Suspense } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AnimatedLayout } from "./components/layout/AnimatedLayout";
import { SafetyDisclaimer } from "./components/common/SafetyDisclaimer";
import { ThemeProvider } from "./components/common/ThemeProvider";
import { ReminderProvider } from "./components/common/ReminderProvider";
import { SereneMindProvider } from "./components/common/SereneMindProvider";
import { ChatErrorBoundary } from "./components/common/ChatErrorBoundary";
import Index from "./pages/Index";
import ChatPage from "./pages/ChatPage";
import ProfilePage from "./pages/ProfilePage";
import PracticesPage from "./pages/PracticesPage";
import PracticeDetailPage from "./pages/PracticeDetailPage";
import NotFound from "./pages/NotFound";
import AuthPage from "./pages/AuthPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import PrivacyPage from "./pages/PrivacyPage";
import TermsPage from "./pages/TermsPage";

// Admin — lazy-loaded so the ~16 admin pages don't ship in the user bundle
const AdminLoginPage = lazy(() => import("./admin/pages/AdminLoginPage"));
const AdminShell = lazy(() => import("./admin/layout/AdminShell").then(m => ({ default: m.AdminShell })));
const OverviewPage = lazy(() => import("./admin/pages/OverviewPage"));
const QueriesPage = lazy(() => import("./admin/pages/QueriesPage"));
const QualityPage = lazy(() => import("./admin/pages/QualityPage"));
const RetrievalPage = lazy(() => import("./admin/pages/RetrievalPage"));
const FeedbackPage = lazy(() => import("./admin/pages/FeedbackPage"));
const DailyTeachingPage = lazy(() => import("./admin/pages/DailyTeachingPage"));
const TriggersPage = lazy(() => import("./admin/pages/TriggersPage"));
const TopicsPage = lazy(() => import("./admin/pages/TopicsPage"));
const PromptsPage = lazy(() => import("./admin/pages/PromptsPage"));
const EvalsPage = lazy(() => import("./admin/pages/EvalsPage"));
const IngestionPage = lazy(() => import("./admin/pages/IngestionPage"));
const LogsPage = lazy(() => import("./admin/pages/LogsPage"));
const AlertsPage = lazy(() => import("./admin/pages/AlertsPage"));
const SettingsPage = lazy(() => import("./admin/pages/SettingsPage"));
const AdminsPage = lazy(() => import("./admin/pages/AdminsPage"));

const queryClient = new QueryClient();

const AdminFallback = () => (
  <div className="min-h-screen flex items-center justify-center bg-background">
    <Loader2 className="w-6 h-6 text-ojas animate-spin" />
  </div>
);

// Admin routes — fully isolated (no Navbar, SafetyDisclaimer, or SereneMind)
const AdminRoutes = () => (
  <Suspense fallback={<AdminFallback />}>
    <Routes>
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="queries" element={<QueriesPage />} />
        <Route path="quality" element={<QualityPage />} />
        <Route path="retrieval" element={<RetrievalPage />} />
        <Route path="feedback" element={<FeedbackPage />} />
        <Route path="daily-teaching" element={<DailyTeachingPage />} />
        <Route path="triggers" element={<TriggersPage />} />
        <Route path="topics" element={<TopicsPage />} />
        <Route path="prompts" element={<PromptsPage />} />
        <Route path="evals" element={<EvalsPage />} />
        <Route path="ingestion" element={<IngestionPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="admins" element={<AdminsPage />} />
      </Route>
    </Routes>
  </Suspense>
);

// End-user routes — wrapped with all providers + error boundary
const UserRoutes = () => (
  <ThemeProvider>
    <ReminderProvider>
      <SereneMindProvider>
        <SafetyDisclaimer />
        <ChatErrorBoundary>
          <AnimatedLayout>
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/auth" element={<AuthPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/terms" element={<TermsPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/practices" element={<PracticesPage />} />
              <Route path="/practices/:slug" element={<PracticeDetailPage />} />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AnimatedLayout>
        </ChatErrorBoundary>
      </SereneMindProvider>
    </ReminderProvider>
  </ThemeProvider>
);

const EndUserApp = () => {
  const loc = useLocation();
  const isAdmin = loc.pathname.startsWith("/admin");
  return isAdmin ? <AdminRoutes /> : <UserRoutes />;
};

const App = () => {
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      console.log('[App] Auth state changed:', event, session?.user?.email);
    });
    return () => subscription.unsubscribe();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Toaster />
          <Sonner />
          <EndUserApp />
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
};

export default App;
