import { useEffect, useRef, useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';
import { clearWhatsAppChallenge, DISCONNECTED_WHATSAPP, normalizeWhatsAppStatus, whatsappRequest, type WhatsAppStatus } from '@/lib/whatsappConnection';

/** Share account-scoped connection state between Profile and the linking page. */
export function useWhatsAppConnection() {
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const current = useRef<Session | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    let authEventSeen = false;
    const apply = (next: Session | null) => {
      if (!alive.current) return;
      if (current.current?.user.id !== next?.user.id) {
        setStatus(null);
        setError(null);
        setBusy(false);
        if (current.current) clearWhatsAppChallenge();
      }
      current.current = next;
      setSession(next);
      setAuthLoading(false);
    };
    supabase.auth.getSession().then(({ data }) => {
      if (!authEventSeen) apply(data.session);
    }).catch(() => {
      if (!authEventSeen) { apply(null); setError('Unable to check sign-in. Please reload this page.'); }
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      authEventSeen = true;
      apply(next);
    });
    return () => { alive.current = false; subscription.unsubscribe(); };
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!session) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    whatsappRequest('status', session.access_token, undefined, controller.signal)
      .then(data => { if (!controller.signal.aborted) setStatus(normalizeWhatsAppStatus(data)); })
      .catch(() => {
        if (!controller.signal.aborted) { setStatus(null); setError('Unable to check WhatsApp connection. Please try again.'); }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [session, authLoading, refresh]);

  async function change(path: string, body: Record<string, unknown>) {
    const owner = current.current;
    if (!owner || busy) return null;
    setBusy(true);
    setError(null);
    const isCurrent = () => alive.current && current.current?.user.id === owner.user.id
      && current.current?.access_token === owner.access_token;
    try {
      const data = await whatsappRequest(path, owner.access_token, body);
      if (!isCurrent()) return null;
      return data;
    } catch (err) {
      if (isCurrent()) setError(err instanceof Error ? err.message : 'Unable to confirm this change. Please try again.');
      return null;
    } finally { if (isCurrent()) setBusy(false); }
  }

  async function verify(code: string, sync: boolean, memory: boolean) {
    const result = await change('verify', { code, sync_history_consent: sync, memory_write_consent: memory });
    if (!result) return false;
    try {
      if (result.success !== true) throw new Error('Connection was not confirmed. Request a fresh link in WhatsApp.');
      setStatus(normalizeWhatsAppStatus({ ...result, linked: true }));
      clearWhatsAppChallenge();
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : 'Connection was not confirmed.'); return false; }
  }

  async function updateConsent(key: 'sync_history_consent' | 'memory_write_consent', value: boolean) {
    const result = await change('consent', { [key]: value });
    if (!result) return false;
    if (result[key] !== value) { setError('Privacy change was not confirmed. Please try again.'); return false; }
    setStatus(prev => prev ? { ...prev, [key]: value } : null);
    return true;
  }

  async function unlink() {
    const result = await change('unlink', {});
    if (!result) return false;
    if (result.success !== true) { setError('Disconnection was not confirmed. Please try again.'); return false; }
    setStatus({ ...DISCONNECTED_WHATSAPP });
    clearWhatsAppChallenge();
    return true;
  }

  return { session, authLoading, status, loading, busy, error, verify, updateConsent, unlink,
    retry: () => setRefresh(value => value + 1) };
}