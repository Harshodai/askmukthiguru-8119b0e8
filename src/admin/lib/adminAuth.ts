// UI-only mock auth. When backend auth is enabled later, this entire file is
// the only thing that changes — function signatures stay identical.
// The real impl will use Supabase auth + a `user_roles` table + `has_role()`
// security-definer RPC. Never store roles on `profiles` — see docs/admin/architecture.md.

const STORAGE_KEY = "admin_session";

export interface AdminSession {
  email: string;
  loggedInAt: string;
}

const DEV_USER = "admin";
const DEV_PASS = "admin";

export async function loginAdmin(
  email: string,
  password: string,
): Promise<{ ok: true; session: AdminSession } | { ok: false; error: string }> {
  await new Promise((r) => setTimeout(r, 250)); // tiny delay for UX
  if (email.trim() !== DEV_USER || password !== DEV_PASS) {
    return { ok: false, error: "Invalid credentials. (Dev mode: admin / admin)" };
  }
  const session: AdminSession = {
    email,
    loggedInAt: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return { ok: true, session };
}

export function logoutAdmin(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function getAdminSession(): AdminSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AdminSession;
  } catch {
    return null;
  }
}

export function isAdminAuthenticated(): boolean {
  return getAdminSession() !== null;
}
