import { useState } from "react";
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
  BarChart3,
  Layers,
  GitBranch,
} from "lucide-react";

import { Sheet, SheetContent, SheetTitle, SheetDescription, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { logoutAdmin, getAdminSession } from "@/admin/lib/adminAuth";
import { useAdminGuard } from "@/admin/hooks/useAdminGuard";
import { AdminTopbar } from "./AdminTopbar";
import { AdminFiltersProvider } from "@/admin/lib/filtersStore";
import { useTranslation } from 'react-i18next';
import { usePageMeta } from '@/hooks/usePageMeta';

const NAV = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/queries", label: "Query Insights", icon: MessagesSquare },
  { to: "/admin/data-sources", label: "Data Sources", icon: Database },
  { to: "/admin/rag-flow", label: "RAG Flow", icon: Network },
  { to: "/admin/content", label: "Content", icon: BookOpen },
  { to: "/admin/evals", label: "Evaluation", icon: ClipboardCheck },
  { to: "/admin/ingestion", label: "Ingestion", icon: Boxes },
  { to: "/admin/telemetry", label: "Observability", icon: Activity },
  { to: "/admin/routing", label: "Routing", icon: GitBranch },
  { to: "/admin/alerts", label: "Reliability", icon: Bell },
  { to: "/admin/feedback", label: "Feedback", icon: ThumbsUp },
  { to: "/admin/settings", label: "Settings", icon: Settings },
  { to: "/admin/admins", label: "Admins", icon: Users },
];


export function AdminShell() {
const { t } = useTranslation();
  const { ready, error, retry } = useAdminGuard();
  const nav = useNavigate();
  const session = getAdminSession();
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  usePageMeta({ title: 'Admin — AskMukthiGuru', noindex: true });

  if (!ready) {
    return (
      <div className="min-h-dvh flex items-center justify-center bg-background text-muted-foreground">
        {error ? <div className="space-y-4 text-center px-6"><p role="alert">{error}</p><Button onClick={retry}>Retry</Button><Button variant="ghost" onClick={async () => { await logoutAdmin(); nav("/admin/login", { replace: true }); }}>Sign out</Button></div> : <span role="status">Verifying admin access…</span>}
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

        {/* Main */}
        <main className="flex-1 min-w-0 flex flex-col">
          <div className="flex items-center bg-card/40 border-b border-border">
            <Sheet open={isMobileOpen} onOpenChange={setIsMobileOpen}>
              <SheetTrigger asChild><Button variant="ghost" size="icon" className="lg:hidden shrink-0 ml-2" aria-label="Open menu"><Menu className="h-5 w-5" /></Button></SheetTrigger>
              <SheetContent side="left" className="w-64 p-0 flex flex-col motion-reduce:animate-none">
                <SheetTitle className="sr-only">Admin navigation</SheetTitle>
                <SheetDescription className="sr-only">Admin Console destinations</SheetDescription>
                {sidebarContent}
              </SheetContent>
            </Sheet>
            <div className="flex-1">
              <AdminTopbar />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </AdminFiltersProvider>
  );
}
