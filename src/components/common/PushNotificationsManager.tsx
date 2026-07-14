import { useEffect, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { PushNotifications, Token, PushNotificationSchema, ActionPerformed } from '@capacitor/push-notifications';
import { Device } from '@capacitor/device';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { BACKEND_URL } from '@/lib/backendUrl';

const TAG = '[PushNotificationsManager]';

export const PushNotificationsManager = () => {
  const navigate = useNavigate();
  const registeredRef = useRef(false);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    let registrationListener: { remove: () => void } | null = null;
    let receivedListener: { remove: () => void } | null = null;
    let actionListener: { remove: () => void } | null = null;
    let disposed = false;

    const registerToken = async (token: string) => {
      try {
        const info = await Device.getInfo();
        const platform = info.platform === 'ios' ? 'ios' : 'android';
        // Derive user identity from the current Supabase session only — never trust a client-supplied user_id.
        const { data: { session } } = await supabase.auth.getSession();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (session?.access_token) headers['Authorization'] = `Bearer ${session.access_token}`;
        const body: Record<string, unknown> = { platform, token };
        const res = await fetch(`${BACKEND_URL}/api/push/register`, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });
        if (!res.ok) console.warn(TAG, 'register failed:', res.status, await res.text());
      } catch (e) {
        console.warn(TAG, 'register error:', e);
      }
    };

    const attachListener = (
      handlePromise: Promise<{ remove: () => void }>,
      assign: (h: { remove: () => void }) => void,
    ) => {
      handlePromise.then((handle) => {
        if (disposed) handle.remove();
        else assign(handle);
      }).catch((e) => console.warn(TAG, 'listener attach error:', e));
    };

    const setup = async () => {
      try {
        let permStatus = await PushNotifications.checkPermissions();
        if (permStatus.receive === 'prompt') {
          permStatus = await PushNotifications.requestPermissions();
        }
        if (permStatus.receive !== 'granted') {
          console.info(TAG, 'push permission not granted');
          return;
        }
        await PushNotifications.register();
        attachListener(
          PushNotifications.addListener('registration', (token: Token) => {
            if (registeredRef.current) return;
            registeredRef.current = true;
            registerToken(token.value);
          }),
          (h) => { registrationListener = h; },
        );
        attachListener(
          PushNotifications.addListener('pushNotificationReceived', (n: PushNotificationSchema) => {
            toast(n.title || 'AskMukthiGuru', { description: n.body });
          }),
          (h) => { receivedListener = h; },
        );
        attachListener(
          PushNotifications.addListener('pushNotificationActionPerformed', (a: ActionPerformed) => {
            const data = a.notification?.data || {};
            if (data.deep_link) navigate(data.deep_link);
            else navigate('/chat');
          }),
          (h) => { actionListener = h; },
        );
      } catch (e) {
        console.warn(TAG, 'setup error:', e);
      }
    };

    setup();

    return () => {
      disposed = true;
      registrationListener?.remove();
      receivedListener?.remove();
      actionListener?.remove();
    };
  }, [navigate]);

  return null;
};