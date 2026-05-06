import { supabase } from '@/integrations/supabase/client';

const STORAGE_KEY = 'admin_session';

export interface AdminSession {
  email: string;
  userId: string;
  loggedInAt: string;
}

/**
 * Verify admin role using Supabase JWT session (not localStorage).
 * Returns true only if a valid Supabase session exists AND user has admin role.
 */
export async function verifyAdminSession(): Promise<{
  authenticated: boolean;
  session: AdminSession | null;
}> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.user) {
    localStorage.removeItem(STORAGE_KEY);
    return { authenticated: false, session: null };
  }

  const { data: roleOk } = await supabase.rpc('has_role', {
    _user_id: session.user.id,
    _role: 'admin',
  });

  if (!roleOk) {
    localStorage.removeItem(STORAGE_KEY);
    return { authenticated: false, session: null };
  }

  const adminSession: AdminSession = {
    email: session.user.email ?? '',
    userId: session.user.id,
    loggedInAt: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(adminSession));
  return { authenticated: true, session: adminSession };
}

export async function loginAdmin(
  email: string,
  password: string,
): Promise<{ ok: true; session: AdminSession } | { ok: false; error: string }> {
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

  if (!roleOk) {
    await supabase.auth.signOut();
    return { ok: false, error: 'Not an admin. Access denied.' };
  }

  const session: AdminSession = {
    email,
    userId: data.user.id,
    loggedInAt: new Date().toISOString(),
  };

  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return { ok: true, session };
}

export async function logoutAdmin(): Promise<void> {
  await supabase.auth.signOut();
  localStorage.removeItem(STORAGE_KEY);
}

/** Get cached display info. NOT for auth decisions — use verifyAdminSession() instead. */
export function getAdminSession(): AdminSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AdminSession;
  } catch {
    return null;
  }
}

/** @deprecated Use verifyAdminSession() for security. */
export function isAdminAuthenticated(): boolean {
  return getAdminSession() !== null;
}
