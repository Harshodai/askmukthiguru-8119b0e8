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

export const CAPABILITIES_CACHE_KEY = 'askmukthiguru_capabilities_cache_v1';
export const CAPABILITIES_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

interface CachedCapabilitiesPayload {
  capabilities: ChatCapabilities;
  timestamp: number;
}

export function readCachedCapabilities(): ChatCapabilities | null {
  if (typeof window === 'undefined') return null;
  try {
    const storage = window.localStorage;
    const raw = storage?.getItem(CAPABILITIES_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CachedCapabilitiesPayload>;
    if (
      parsed &&
      typeof parsed.timestamp === 'number' &&
      parsed.capabilities &&
      typeof parsed.capabilities === 'object'
    ) {
      if (Date.now() - parsed.timestamp < CAPABILITIES_CACHE_TTL_MS) {
        const caps = parsed.capabilities as Record<string, unknown>;
        const allValid = (Object.keys(LOCAL_CHAT_CAPABILITIES) as Array<keyof ChatCapabilities>).every(
          (key) => typeof caps[key] === 'boolean'
        );
        if (allValid) {
          return parsed.capabilities as ChatCapabilities;
        }
      }
    }
  } catch {
    // Corrupt cache or storage error falls through
  }
  return null;
}

export function writeCachedCapabilities(capabilities: ChatCapabilities): void {
  if (typeof window === 'undefined') return;
  try {
    const payload: CachedCapabilitiesPayload = {
      capabilities,
      timestamp: Date.now(),
    };
    const storage = window.localStorage;
    storage?.setItem(CAPABILITIES_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Storage quota or private browsing error ignored
  }
}

export function resetCapabilitiesCache(): void {
  if (typeof window === 'undefined') return;
  try {
    const storage = window.localStorage;
    storage?.removeItem(CAPABILITIES_CACHE_KEY);
  } catch {
    // Ignore
  }
}

/**
 * Fetches only public enablement state; uses 24h localStorage cache to prevent
 * waking Serverless backends on routine page visits and mounts.
 */
export function useChatCapabilities(): { capabilities: ChatCapabilities; manifestReady: boolean } {
  const [capabilities, setCapabilities] = useState<ChatCapabilities>(() => {
    return readCachedCapabilities() ?? LOCAL_CHAT_CAPABILITIES;
  });
  const [manifestReady, setManifestReady] = useState<boolean>(() => {
    return readCachedCapabilities() !== null;
  });

  useEffect(() => {
    // If a fresh cached capability manifest is already available, skip the network request entirely.
    // This allows the Railway Serverless container to stay asleep and prevents $35+/mo billing.
    const cached = readCachedCapabilities();
    if (cached) {
      setCapabilities(cached);
      setManifestReady(true);
      return;
    }

    const endpoint = capabilityEndpoint();
    if (!endpoint) return;
    const controller = new AbortController();
    void fetch(endpoint, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`capability status ${response.status}`);
        const payload = await response.json() as { ready?: boolean; capabilities?: CapabilityManifest };
        if (payload.ready !== true) throw new Error('capability manifest not ready');
        const resolved = resolveChatCapabilities(payload.capabilities);
        setCapabilities(resolved);
        setManifestReady(true);
        writeCachedCapabilities(resolved);
      })
      .catch(() => {
        // Network loss must not turn browser-local, already-working controls into dead UI.
      });
    return () => controller.abort();
  }, []);

  return { capabilities, manifestReady };
}
