import { supabase } from '@/integrations/supabase/client';

const STORAGE_KEY = 'admin_session';

export interface AdminSession {
  email: string;
  userId: string;
  loggedInAt: string;
}

function getSafeSessionStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' && window.sessionStorage ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

/**
 * Verify admin role using Supabase JWT session (not storage).
 * Returns true only if a valid Supabase session exists AND user has admin role.
 */
export async function verifyAdminSession(): Promise<{
  authenticated: boolean;
  session: AdminSession | null;
}> {
  const storage = getSafeSessionStorage();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.user) {
    storage?.removeItem(STORAGE_KEY);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
    return { authenticated: false, session: null };
  }

  const { data: roleOk } = await supabase.rpc('has_role', {
    _user_id: session.user.id,
    _role: 'admin',
  });

  // Type guard: RPC must return boolean true, not truthy/undefined/null
  if (roleOk !== true) {
    storage?.removeItem(STORAGE_KEY);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
    return { authenticated: false, session: null };
  }

  const adminSession: AdminSession = {
    email: session.user.email ?? '',
    userId: session.user.id,
    loggedInAt: new Date().toISOString(),
  };
  storage?.setItem(STORAGE_KEY, JSON.stringify(adminSession));
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
  return { authenticated: true, session: adminSession };
}

export async function loginAdmin(
  email: string,
  password: string,
): Promise<{ ok: true; session: AdminSession } | { ok: false; error: string }> {
  const storage = getSafeSessionStorage();
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    return { ok: false, error: error.message };
  }

  const { data: roleOk } = await supabase.rpc('has_role', {
    _user_id: data.user.id,
    _role: 'admin',
  });

  if (roleOk !== true) {
    await supabase.auth.signOut();
    return { ok: false, error: 'Not an admin. Access denied.' };
  }

  const session: AdminSession = {
    email,
    userId: data.user.id,
    loggedInAt: new Date().toISOString(),
  };

  storage?.setItem(STORAGE_KEY, JSON.stringify(session));
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
  return { ok: true, session };
}

export async function logoutAdmin(): Promise<void> {
  const storage = getSafeSessionStorage();
  await supabase.auth.signOut();
  storage?.removeItem(STORAGE_KEY);
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
}

/** Get cached display info. NOT for auth decisions — use verifyAdminSession() instead. */
export function getAdminSession(): AdminSession | null {
  try {
    const storage = getSafeSessionStorage();
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AdminSession;
  } catch {
    return null;
  }
}
