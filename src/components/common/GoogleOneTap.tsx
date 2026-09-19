import { useEffect, useRef } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';
import { GOOGLE_GSI_SDK_URL, GOOGLE_CLIENT_ID_FALLBACK } from '@/lib/authConstants';

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

async function sha256Hex(input: string): Promise<string | null> {
  const webCrypto = typeof window !== 'undefined' ? window.crypto : undefined;
  if (!webCrypto?.subtle) {
    // Google One Tap requires a hashed nonce. On an insecure Docker/test
    // origin Web Crypto may be unavailable; skip the optional prompt rather
    // than throwing a page-level error or weakening nonce validation.
    return null;
  }
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await webCrypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export const GoogleOneTap = () => {
  const { status } = useAuthStatus();
  const { toast } = useToast();
  const { t } = useTranslation();
  const initialized = useRef(false);
  const nonce = useRef('');
  // Same double-callback race as AuthPage.tsx's handleGoogleOneTapResponse:
  // GSI can invoke this callback twice for one sign-in. Without these guards,
  // a second, sequential callback reuses an already-consumed nonce, throws
  // "Nonces mismatch", and — because this component previously only
  // console.error'd on failure with no toast on success either — the whole
  // interaction looked silently broken even when the first callback had
  // already signed the user in. Reported live 2026-09-19.
  const inFlightRef = useRef(false);
  const justSucceededRef = useRef(false);

  useEffect(() => {
    if (status !== 'anonymous' || initialized.current) return;

    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || GOOGLE_CLIENT_ID_FALLBACK;
    if (typeof window !== 'undefined' && !window.isSecureContext) return;

    let script = document.querySelector(`script[src="${GOOGLE_GSI_SDK_URL}"]`) as HTMLScriptElement;
    if (!script) {
      script = document.createElement('script');
      script.src = GOOGLE_GSI_SDK_URL;
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }

    const initGSI = () => {
      const g = window.google;
      if (!g || initialized.current) return;
      const rawNonce = generateNonce();

      sha256Hex(rawNonce).then(hashedNonce => {
        if (!hashedNonce || initialized.current) return;
        initialized.current = true;
        nonce.current = hashedNonce;

        g.accounts.id.initialize({
          client_id: clientId,
          callback: async (response) => {
            if (inFlightRef.current) return;
            inFlightRef.current = true;
            try {
              const { error } = await supabase.auth.signInWithIdToken({
                provider: 'google',
                token: response.credential,
                nonce: hashedNonce,
              });
              if (error) throw error;
              justSucceededRef.current = true;
              setTimeout(() => { justSucceededRef.current = false; }, 5000);
              toast({ title: t('auth.welcomeBack'), description: t('auth.signedInOneTap') });
            } catch (err) {
              const msg = err instanceof Error ? err.message : String(err);
              console.error('[Google OneTap] Sign-in failed:', err);
              if (msg.includes('Nonces mismatch') || msg.includes('nonce')) {
                if (justSucceededRef.current) return;
                for (const delayMs of [0, 150, 400]) {
                  if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs));
                  const { data: { session } } = await supabase.auth.getSession();
                  if (session) return;
                }
              }
              toast({ title: t('auth.oneTapFailed'), variant: 'destructive' });
            } finally {
              inFlightRef.current = false;
            }
          },
          auto_select: true,
          cancel_on_tap_outside: true,
          itp_support: true,
          nonce: hashedNonce,
        });

        g.accounts.id.prompt();
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
