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
  { to: "/admin/feedback", label: "Feedback", icon: ThumbsUp },
  { to: "/admin/triggers", label: "Triggers", icon: Activity },
  { to: "/admin/topics", label: "Topics", icon: Sparkles },
  { to: "/admin/prompts", label: "Prompts", icon: FileText },
  { to: "/admin/evals", label: "Evals", icon: ClipboardCheck },
  { to: "/admin/ingestion", label: "Ingestion", icon: Boxes },
  { to: "/admin/logs", label: "Logs", icon: ScrollText },
  { to: "/admin/alerts", label: "Alerts", icon: Bell },
  { to: "/admin/settings", label: "Settings", icon: Settings },
  { to: "/admin/admins", label: "Admins", icon: Users },
];

export function AdminShell() {
  const { ready } = useAdminGuard();
  const nav = useNavigate();
  const session = getAdminSession();

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
        Loading admin…
      </div>
    );
  }

  return (
    <AdminFiltersProvider>
      <div className="min-h-screen bg-background text-foreground flex">
        {/* Sidebar */}
        <aside className="w-60 shrink-0 border-r border-border bg-card flex flex-col">
          <div className="px-5 py-5 border-b border-border">
            <div className="text-xs uppercase tracking-widest text-muted-foreground">
              AskMukthiGuru
            </div>
            <div className="text-lg font-semibold mt-1">Admin Console</div>
          </div>
          <nav className="flex-1 overflow-y-auto py-3">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
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
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0 flex flex-col">
          <AdminTopbar />
          <div className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </AdminFiltersProvider>
  );
}
