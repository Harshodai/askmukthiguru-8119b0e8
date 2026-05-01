import { supabase } from './supabaseClient';

const STORAGE_KEY = "admin_session";

export interface AdminSession {
  email: string;
  loggedInAt: string;
}

export async function loginAdmin(
  email: string,
  password: string,
): Promise<{ ok: true; session: AdminSession } | { ok: false; error: string }> {
  
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  
  if (error) {
    return { ok: false, error: error.message };
  }
  
  // Verify admin role
  const { data: roleOk } = await supabase.rpc("has_role", {
    _user_id: data.user.id, 
    _role: "admin",
  });
  
  if (!roleOk) {
    await supabase.auth.signOut();
    return { ok: false, error: "Not an admin. Access denied." };
  }
  
  const session: AdminSession = {
    email,
    loggedInAt: new Date().toISOString(),
  };
  
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return { ok: true, session };
}

export async function logoutAdmin(): Promise<void> {
  await supabase.auth.signOut();
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
