import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { isAdminAuthenticated } from "@/admin/lib/adminAuth";

export function useAdminGuard(): { ready: boolean } {
  const nav = useNavigate();
  const loc = useLocation();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isAdminAuthenticated()) {
      nav(`/admin/login?redirect=${encodeURIComponent(loc.pathname)}`, { replace: true });
    } else {
      setReady(true);
    }
  }, [nav, loc.pathname]);

  return { ready };
}
