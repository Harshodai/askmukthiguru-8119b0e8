import { useEffect, useRef } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { GOOGLE_GSI_SDK_URL } from '@/lib/authConstants';

function generateNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  if (typeof window !== 'undefined' && window.crypto) {
    const values = new Uint32Array(16);
    window.crypto.getRandomValues(values);
    for (let i = 0; i < values.length; i++) {
      nonce += chars[values[i] % chars.length];
    }
  }
  return nonce;
}

async function sha256Hex(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export const GoogleOneTap = () => {
  const { status } = useAuthStatus();
  const initialized = useRef(false);
  const nonce = useRef('');

  useEffect(() => {
    if (status !== 'anonymous' || initialized.current) return;

    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) return;

    let script = document.querySelector(`script[src="${GOOGLE_GSI_SDK_URL}"]`) as HTMLScriptElement;
    if (!script) {
      script = document.createElement('script');
      script.src = GOOGLE_GSI_SDK_URL;
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }

    const initGSI = () => {
      if (typeof window.google === 'undefined' || initialized.current) return;
      initialized.current = true;
      const rawNonce = generateNonce();

      sha256Hex(rawNonce).then(hashedNonce => {
        nonce.current = hashedNonce;

        window.google.accounts.id.initialize({
          client_id: clientId,
          nonce: hashedNonce,
          callback: async (response) => {
            try {
              const { error } = await supabase.auth.signInWithIdToken({
                provider: 'google',
                token: response.credential,
                nonce: hashedNonce,
              });
              if (error) throw error;
            } catch (err) {
              console.error('[Google OneTap] Sign-in failed:', err);
            }
          },
          auto_select: true,
          cancel_on_tap_outside: true,
          data_fedcm: true,
        });

        window.google.accounts.id.prompt();
      });
    };

    if (typeof window.google !== 'undefined') {
      initGSI();
    } else {
      script.addEventListener('load', initGSI);
      return () => script.removeEventListener('load', initGSI);
    }
  }, [status]);

  return null;
};
