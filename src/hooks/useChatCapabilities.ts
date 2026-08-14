import { useEffect, useState } from 'react';
import { getCurrentConfig } from '@/lib/chat/config';

type CapabilityState = 'available' | 'unavailable' | 'disabled_by_policy';
type CapabilityManifest = {
  features?: Record<string, CapabilityState>;
};

export type ChatCapabilities = {
  sereneMind: boolean;
  guidedMeditation: boolean;
  textAttachments: boolean;
  voiceInput: boolean;
  googleSso: boolean;
  pushNotifications: boolean;
};

export const LOCAL_CHAT_CAPABILITIES: ChatCapabilities = {
  sereneMind: true,
  guidedMeditation: true,
  textAttachments: true,
  voiceInput: true,
  googleSso: true,
  pushNotifications: true,
};

export function resolveChatCapabilities(manifest?: CapabilityManifest): ChatCapabilities {
  const features = manifest?.features;
  if (!features) return LOCAL_CHAT_CAPABILITIES;
  const isAvailable = (key: string, fallback: boolean) =>
    features[key] === undefined ? fallback : features[key] === 'available';
  return {
    sereneMind: isAvailable('serene_mind', LOCAL_CHAT_CAPABILITIES.sereneMind),
    guidedMeditation: isAvailable('guided_meditation', LOCAL_CHAT_CAPABILITIES.guidedMeditation),
    textAttachments: isAvailable('text_attachments', LOCAL_CHAT_CAPABILITIES.textAttachments),
    voiceInput: isAvailable('voice_input', LOCAL_CHAT_CAPABILITIES.voiceInput),
    googleSso: isAvailable('google_sso', LOCAL_CHAT_CAPABILITIES.googleSso),
    pushNotifications: isAvailable('push_notifications', LOCAL_CHAT_CAPABILITIES.pushNotifications),
  };
}

function capabilityEndpoint(): string | null {
  const endpoint = getCurrentConfig().endpoint;
  if (!endpoint || typeof window === 'undefined') return null;
  try {
    return new URL('/api/capabilities', new URL(endpoint, window.location.origin).origin).href;
  } catch {
    return null;
  }
}

/** Fetches only public enablement state; failed fetches retain working local controls. */
export function useChatCapabilities(): { capabilities: ChatCapabilities; manifestReady: boolean } {
  const [capabilities, setCapabilities] = useState<ChatCapabilities>(LOCAL_CHAT_CAPABILITIES);
  const [manifestReady, setManifestReady] = useState(false);

  useEffect(() => {
    const endpoint = capabilityEndpoint();
    if (!endpoint) return;
    const controller = new AbortController();
    void fetch(endpoint, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`capability status ${response.status}`);
        const payload = await response.json() as { ready?: boolean; capabilities?: CapabilityManifest };
        if (payload.ready !== true) throw new Error('capability manifest not ready');
        setCapabilities(resolveChatCapabilities(payload.capabilities));
        setManifestReady(true);
      })
      .catch(() => {
        // Network loss must not turn browser-local, already-working controls into dead UI.
      });
    return () => controller.abort();
  }, []);

  return { capabilities, manifestReady };
}
