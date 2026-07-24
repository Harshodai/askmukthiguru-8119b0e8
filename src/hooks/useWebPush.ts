/**
 * useWebPush — register a push-only service worker, subscribe via VAPID,
 * and persist the subscription to Supabase. Safe to call in browsers that
 * don't support Push (will simply return supported=false).
 */
import { useCallback, useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';

const SW_PATH = '/push-sw.js';
const VAPID_PUBLIC_KEY = (import.meta.env.VITE_VAPID_PUBLIC_KEY as string | undefined) ?? '';

const urlBase64ToUint8Array = (base64String: string): Uint8Array => {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
};

const arrayBufferToBase64 = (buffer: ArrayBuffer | null): string => {
  if (!buffer) return '';
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
};

export interface WebPushState {
  supported: boolean;
  permission: NotificationPermission | 'unsupported';
  subscribed: boolean;
  loading: boolean;
  error: string | null;
}

export const useWebPush = () => {
  const [state, setState] = useState<WebPushState>({
    supported: false,
    permission: 'default',
    subscribed: false,
    loading: false,
    error: null,
  });

  useEffect(() => {
    const supported =
      typeof window !== 'undefined' &&
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window;
    if (!supported) {
      setState((s) => ({ ...s, supported: false, permission: 'unsupported' }));
      return;
    }
    (async () => {
      const reg = await navigator.serviceWorker.getRegistration(SW_PATH);
      const existing = reg ? await reg.pushManager.getSubscription() : null;
      setState((s) => ({
        ...s,
        supported: true,
        permission: Notification.permission,
        subscribed: Boolean(existing),
      }));
    })();
  }, []);

  const subscribe = useCallback(async (): Promise<boolean> => {
    if (!VAPID_PUBLIC_KEY) {
      setState((s) => ({ ...s, error: 'VAPID public key missing' }));
      return false;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setState((s) => ({ ...s, loading: false, permission }));
        return false;
      }
      const reg =
        (await navigator.serviceWorker.getRegistration(SW_PATH)) ??
        (await navigator.serviceWorker.register(SW_PATH));
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY).buffer as ArrayBuffer,
      });
      const json = sub.toJSON();
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        setState((s) => ({ ...s, loading: false, error: 'not_authenticated' }));
        return false;
      }
      await supabase.from('push_subscriptions').upsert(
        {
          user_id: session.user.id,
          endpoint: sub.endpoint,
          p256dh: (json.keys && json.keys.p256dh) || arrayBufferToBase64(sub.getKey('p256dh')),
          auth: (json.keys && json.keys.auth) || arrayBufferToBase64(sub.getKey('auth')),
        },
        { onConflict: 'user_id,endpoint' },
      );
      setState({ supported: true, permission: 'granted', subscribed: true, loading: false, error: null });
      return true;
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e instanceof Error ? e.message : 'subscribe_failed' }));
      return false;
    }
  }, []);

  const unsubscribe = useCallback(async (): Promise<void> => {
    const reg = await navigator.serviceWorker.getRegistration(SW_PATH);
    const sub = reg ? await reg.pushManager.getSubscription() : null;
    if (sub) {
      const endpoint = sub.endpoint;
      await sub.unsubscribe();
      await supabase.from('push_subscriptions').delete().eq('endpoint', endpoint);
    }
    setState((s) => ({ ...s, subscribed: false }));
  }, []);

  return { ...state, subscribe, unsubscribe };
};
