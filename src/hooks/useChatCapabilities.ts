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
  documentAttachments: boolean;
  imageAttachments: boolean;
  audioAttachments: boolean;
  videoAttachments: boolean;
  ocr: boolean;
  voiceInput: boolean;
  googleSso: boolean;
  pushNotifications: boolean;
};

export const LOCAL_CHAT_CAPABILITIES: ChatCapabilities = {
  sereneMind: true,
  guidedMeditation: true,
  textAttachments: true,
  documentAttachments: true,
  imageAttachments: true,
  audioAttachments: true,
  videoAttachments: true,
  ocr: true,
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
    documentAttachments: isAvailable('document_attachments', LOCAL_CHAT_CAPABILITIES.documentAttachments),
    imageAttachments: isAvailable('image_attachments', LOCAL_CHAT_CAPABILITIES.imageAttachments),
    audioAttachments: isAvailable('audio_attachments', LOCAL_CHAT_CAPABILITIES.audioAttachments),
    videoAttachments: isAvailable('video_attachments', LOCAL_CHAT_CAPABILITIES.videoAttachments),
    ocr: isAvailable('ocr', LOCAL_CHAT_CAPABILITIES.ocr),
    voiceInput: isAvailable('voice_input', LOCAL_CHAT_CAPABILITIES.voiceInput),
    googleSso: isAvailable('google_sso', LOCAL_CHAT_CAPABILITIES.googleSso),
    pushNotifications: isAvailable('push_notifications', LOCAL_CHAT_CAPABILITIES.pushNotifications),
  };
}

function capabilityEndpoint(): string | null {
  const endpoint = getCurrentConfig().endpoint;
  if (!endpoint || typeof window === 'undefined') return null;
  try {
    const configuredOrigin = new URL(endpoint, window.location.origin).origin;
    const explicitBackend = Boolean(import.meta.env.VITE_BACKEND_URL?.trim());
    const configuredUrl = new URL(configuredOrigin);
    const isLoopbackOrigin =
      configuredUrl.hostname === 'localhost' ||
      configuredUrl.hostname === '127.0.0.1' ||
      configuredUrl.hostname === '[::1]';

    // A stale runtime chat override must not send a hosted/browser request to
    // the developer's localhost. Docker and reverse-proxy deployments use the
    // same-origin /api proxy unless an explicit backend URL was built in.
    const origin = !explicitBackend && !import.meta.env.DEV && isLoopbackOrigin
      ? window.location.origin
      : configuredOrigin;
    return new URL('/api/capabilities', origin).href;
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
