import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  MessagesSquare,
  ShieldCheck,
  Database,
  Activity,
  Sparkles,
  FileText,
  ClipboardCheck,
  Boxes,
  ScrollText,
  Bell,
  Settings,
  Users,
  LogOut,
  ThumbsUp,
  Image,
  ListOrdered,
  Network,
  BookOpen,
  LineChart,
  Quote,
  Menu,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { logoutAdmin, getAdminSession } from "@/admin/lib/adminAuth";
import { useAdminGuard } from "@/admin/hooks/useAdminGuard";
import { AdminTopbar } from "./AdminTopbar";
import { AdminFiltersProvider } from "@/admin/lib/filtersStore";

const NAV = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/queries", label: "Queries", icon: MessagesSquare },
  { to: "/admin/quality", label: "Quality", icon: ShieldCheck },
  { to: "/admin/retrieval", label: "Retrieval", icon: Database },
  { to: "/admin/rag-flow", label: "RAG Flow", icon: Network },
  { to: "/admin/feedback", label: "Feedback", icon: ThumbsUp },
  { to: "/admin/daily-teaching", label: "Daily Teaching", icon: Image },
  { to: "/admin/teaching-tips", label: "Teaching Tips", icon: Quote },
  { to: "/admin/triggers", label: "Triggers", icon: Activity },
  { to: "/admin/topics", label: "Topics", icon: Sparkles },
  { to: "/admin/prompts", label: "Prompts", icon: FileText },
  { to: "/admin/evals", label: "Evals", icon: ClipboardCheck },
  { to: "/admin/queue", label: "Queue", icon: ListOrdered },
  { to: "/admin/ingestion", label: "Ingestion", icon: Boxes },
  { to: "/admin/logs", label: "Logs", icon: ScrollText },
  { to: "/admin/telemetry", label: "Telemetry", icon: Activity },
  { to: "/admin/monitoring", label: "Monitoring", icon: LineChart },
  { to: "/admin/alerts", label: "Alerts", icon: Bell },
  { to: "/admin/settings", label: "Settings", icon: Settings },
  { to: "/admin/admins", label: "Admins", icon: Users },
  { to: "/admin/okf", label: "OKF", icon: BookOpen },
];

export function AdminShell() {
  const { ready } = useAdminGuard();
  const nav = useNavigate();
  const session = getAdminSession();
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  if (!ready) {
    return (
      <div className="min-h-dvh flex items-center justify-center bg-background text-muted-foreground">
        Loading admin…
      </div>
    );
  }

  const sidebarContent = (
    <>
      <div className="px-5 py-5 border-b border-border flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground">
            AskMukthiGuru
          </div>
          <div className="text-lg font-semibold mt-1">Admin Console</div>
        </div>
        <button
          onClick={() => setIsMobileOpen(false)}
          className="lg:hidden p-1.5 rounded-full hover:bg-muted text-muted-foreground transition-colors"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setIsMobileOpen(false)}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-5 py-2 text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary border-r-2 border-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t border-border space-y-2">
        <div className="px-2 text-xs text-muted-foreground truncate">
          {session?.email}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start"
          onClick={async () => {
            await logoutAdmin();
            nav("/admin/login", { replace: true });
          }}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </>
  );

  return (
    <AdminFiltersProvider>
      <div className="min-h-dvh bg-background text-foreground flex relative overflow-x-hidden">
        {/* Desktop Sidebar */}
        <aside className="hidden lg:flex w-60 shrink-0 border-r border-border bg-card flex-col">
          {sidebarContent}
        </aside>

        {/* Mobile Sidebar Slide-over */}
        <AnimatePresence>
          {isMobileOpen && (
            <>
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.4 }}
                exit={{ opacity: 0 }}
                onClick={() => setIsMobileOpen(false)}
                className="fixed inset-0 bg-black/40 z-40 lg:hidden"
              />
              {/* Drawer */}
              <motion.aside
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ type: "spring", damping: 25, stiffness: 200 }}
                className="fixed inset-y-0 left-0 w-60 bg-card border-r border-border z-50 flex flex-col lg:hidden"
              >
                {sidebarContent}
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        {/* Main */}
        <main className="flex-1 min-w-0 flex flex-col">
          <div className="flex items-center bg-card/40 border-b border-border">
            <button
              onClick={() => setIsMobileOpen(true)}
              className="lg:hidden p-2 ml-4 rounded-md hover:bg-muted text-muted-foreground transition-colors"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex-1">
              <AdminTopbar />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </AdminFiltersProvider>
  );
}
