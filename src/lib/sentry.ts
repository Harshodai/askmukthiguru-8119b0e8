import * as Sentry from "@sentry/react";

const DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined;

/** Sentry is enabled only when a DSN is configured AND this is a production
 *  build. No hostname gating: Railway-served SPAs and native WebViews
 *  (localhost inside Capacitor) must report too. */
export function sentryEnabled(): boolean {
  return Boolean(DSN && DSN.trim()) && Boolean(import.meta.env.PROD);
}

export function initSentry() {
  if (!sentryEnabled()) return;

  Sentry.init({
    dsn: DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0.5,
    // P1-FE-14: the error-replay DOM capture includes the chat UI, which holds
    // personal/spiritual questions. Mask all text, block media, and mask input
    // fields so replay frames never expose chat content.
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
        maskAllInputs: true,
      }),
    ],
    // Filter noisy/expected errors
    ignoreErrors: [
      "ResizeObserver loop limit exceeded",
      "ResizeObserver loop completed with undelivered notifications",
      "NetworkError when attempting to fetch resource",
      "Failed to fetch",
      "AbortError",
    ],
  });
}

/** Add a pageview breadcrumb for session timeline visibility. */
export function trackPageview(path: string) {
  if (!sentryEnabled()) return;
  Sentry.addBreadcrumb({
    category: "navigation",
    message: path,
    level: "info",
  });
}

/** Tag an error with a feature area for actionable stack traces. */
export function captureFeatureError(
  err: unknown,
  feature: "chat" | "translation" | "language" | "meditation" | "auth",
  extra?: Record<string, unknown>,
) {
  if (!sentryEnabled()) {
    console.error(`[${feature}]`, err, extra);
    return;
  }
  Sentry.withScope((scope) => {
    scope.setTag("feature", feature);
    if (extra) scope.setContext("extra", extra);
    Sentry.captureException(err);
  });
}
