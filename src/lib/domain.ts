/**
 * Centralized public-domain configuration.
 *
 * Vercel must set VITE_PUBLIC_APP_URL to the canonical HTTPS domain before
 * production launch. During local/preview browsing, the current origin is
 * safer than emitting a retired hosting provider URL. The build-time fallback
 * is the intended custom domain and should be replaced by the environment
 * variable when the owner chooses a different public hostname.
 */
const configuredDomain =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_PUBLIC_APP_URL) || '';
const browserOrigin =
  typeof window !== 'undefined' && window.location.origin.startsWith('http')
    ? window.location.origin
    : '';

export const PRODUCTION_DOMAIN = (configuredDomain || browserOrigin || 'https://askmukthiguru.com')
  .trim()
  .replace(/\/+$/, '');
export const PRODUCTION_OG_IMAGE = `${PRODUCTION_DOMAIN}/og-image.png`;
export const PRODUCTION_ICON = `${PRODUCTION_DOMAIN}/icon-512.png`;

/** Build a full URL for a given path. */
export const buildUrl = (path: string): string => {
  if (path.startsWith('http')) return path;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${PRODUCTION_DOMAIN}${cleanPath}`;
};

/** Build canonical URL for a page. */
export const buildCanonical = (path: string): string => buildUrl(path);

/** Get the hostname from the configured public domain. */
export const getHostname = (): string => new URL(PRODUCTION_DOMAIN).hostname;

/** Get support email. */
export const getSupportEmail = (): string => `support@${getHostname()}`;

/** Get privacy email. */
export const getPrivacyEmail = (): string => `privacy@${getHostname()}`;

/** Get hello email. */
export const getHelloEmail = (): string => `hello@${getHostname()}`;
