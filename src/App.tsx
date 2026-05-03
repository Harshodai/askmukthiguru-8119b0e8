import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { AnimatedLayout } from "./components/layout/AnimatedLayout";
import { SafetyDisclaimer } from "./components/common/SafetyDisclaimer";
import { ThemeProvider } from "./components/common/ThemeProvider";
import { ReminderProvider } from "./components/common/ReminderProvider";
import { SereneMindProvider } from "./components/common/SereneMindProvider";
import Index from "./pages/Index";
import ChatPage from "./pages/ChatPage";
import ProfilePage from "./pages/ProfilePage";
import PracticesPage from "./pages/PracticesPage";
import PracticeDetailPage from "./pages/PracticeDetailPage";
import NotFound from "./pages/NotFound";

// Admin
import AdminLoginPage from "./admin/pages/AdminLoginPage";
import { AdminShell } from "./admin/layout/AdminShell";
import OverviewPage from "./admin/pages/OverviewPage";
import QueriesPage from "./admin/pages/QueriesPage";
import QualityPage from "./admin/pages/QualityPage";
import RetrievalPage from "./admin/pages/RetrievalPage";
import FeedbackPage from "./admin/pages/FeedbackPage";
import TriggersPage from "./admin/pages/TriggersPage";
import TopicsPage from "./admin/pages/TopicsPage";
import PromptsPage from "./admin/pages/PromptsPage";
import EvalsPage from "./admin/pages/EvalsPage";
import IngestionPage from "./admin/pages/IngestionPage";
import LogsPage from "./admin/pages/LogsPage";
import AlertsPage from "./admin/pages/AlertsPage";
import SettingsPage from "./admin/pages/SettingsPage";
import AdminsPage from "./admin/pages/AdminsPage";

const queryClient = new QueryClient();

// Wraps the end-user app shell. Excluded for /admin routes so the admin
// console is fully isolated (no Navbar, no SafetyDisclaimer, no SereneMind, etc.).
const EndUserApp = () => {
  const loc = useLocation();
  const isAdmin = loc.pathname.startsWith("/admin");
  if (isAdmin) {
    return (
      <Routes>
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="queries" element={<QueriesPage />} />
          <Route path="quality" element={<QualityPage />} />
          <Route path="retrieval" element={<RetrievalPage />} />
          <Route path="feedback" element={<FeedbackPage />} />
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
    );
  }
  return (
    <ThemeProvider>
      <ReminderProvider>
        <SereneMindProvider>
          <SafetyDisclaimer />
          <AnimatedLayout>
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/practices" element={<PracticesPage />} />
              <Route path="/practices/:slug" element={<PracticeDetailPage />} />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AnimatedLayout>
        </SereneMindProvider>
      </ReminderProvider>
    </ThemeProvider>
  );
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <EndUserApp />
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
