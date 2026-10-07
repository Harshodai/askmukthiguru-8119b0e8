/**
 * Centralized public-domain configuration.
 *
 * PUBLIC_APP_URL is the one URL faculty and seekers open. It is the Lovable
 * host until the owner approves launch and buys a custom domain; when that
 * happens, change it here and in the places `src/test/publicAppUrl.test.ts`
 * checks (index.html, public/robots.txt, public/sitemap.xml, the CORS origin in
 * deploy_railway.sh, .env.example). That test fails if any of them drift.
 *
 * VITE_PUBLIC_APP_URL still overrides it per build. During local or preview
 * browsing the current origin is used, so share links point where you are.
 *
 * The backend URL is separate: a Lovable build must set VITE_BACKEND_URL,
 * because `backendUrl.ts` deliberately does not send Lovable hosts to the
 * production backend by hostname alone.
 */
export const PUBLIC_APP_URL = 'https://askmukthiguru.lovable.app';

const configuredDomain =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_PUBLIC_APP_URL) || '';
const browserOrigin =
  typeof window !== 'undefined' && window.location.origin.startsWith('http')
    ? window.location.origin
    : '';

export const PRODUCTION_DOMAIN = (configuredDomain || browserOrigin || PUBLIC_APP_URL)
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

/**
 * The one inbox for privacy, support and general mail, chosen by the owner
 * until the custom domain exists. These addresses used to be derived from the
 * host, which on Lovable produced privacy@askmukthiguru.lovable.app: an
 * address nobody receives. VITE_CONTACT_EMAIL overrides it per build.
 */
export const CONTACT_EMAIL = 'kharshaengineer@gmail.com';

const configuredContact =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_CONTACT_EMAIL) || '';
const contactEmail = (): string => configuredContact.trim() || CONTACT_EMAIL;

/** Get support email. */
export const getSupportEmail = (): string => contactEmail();

/** Get privacy email. */
export const getPrivacyEmail = (): string => contactEmail();

/** Get hello email. */
export const getHelloEmail = (): string => contactEmail();
