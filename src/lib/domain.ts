/**
 * Centralized domain configuration.
 * Change this when the production domain is purchased/configured.
 * Currently using Lovable preview domain since .com is not yet purchased.
 */

export const PRODUCTION_DOMAIN = 'https://askmukthiguru.lovable.app';
export const PRODUCTION_OG_IMAGE = `${PRODUCTION_DOMAIN}/og-image.png`;
export const PRODUCTION_ICON = `${PRODUCTION_DOMAIN}/icon-512.png`;

/**
 * Build a full URL for a given path
 */
export const buildUrl = (path: string): string => {
  if (path.startsWith('http')) return path;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${PRODUCTION_DOMAIN}${cleanPath}`;
};

/**
 * Build canonical URL for a page
 */
export const buildCanonical = (path: string): string => {
  if (path.startsWith('http')) return path;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${PRODUCTION_DOMAIN}${cleanPath}`;
};

/**
 * Get the hostname from the production domain
 */
export const getHostname = (): string => new URL(PRODUCTION_DOMAIN).hostname;

/**
 * Get support email
 */
export const getSupportEmail = (): string => `support@${getHostname()}`;

/**
 * Get privacy email
 */
export const getPrivacyEmail = (): string => `privacy@${getHostname()}`;

/**
 * Get hello email
 */
export const getHelloEmail = (): string => `hello@${getHostname()}`;