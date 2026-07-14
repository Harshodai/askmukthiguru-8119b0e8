import * as Sentry from "@sentry/react";

const DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined;

const isProdHost = typeof window !== "undefined"
  && /askmukthiguru\.lovable\.app$|\.lovable\.app$/.test(window.location.hostname);

export function initSentry() {
  if (!DSN || !isProdHost) return;

  Sentry.init({
    dsn: DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0.5,
    integrations: [Sentry.browserTracingIntegration(), Sentry.replayIntegration()],
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

/** Tag an error with a feature area for actionable stack traces. */
export function captureFeatureError(
  err: unknown,
  feature: "chat" | "translation" | "language" | "meditation" | "auth",
  extra?: Record<string, unknown>,
) {
  if (!DSN || !isProdHost) {
    // eslint-disable-next-line no-console
    console.error(`[${feature}]`, err, extra);
    return;
  }
  Sentry.withScope((scope) => {
    scope.setTag("feature", feature);
    if (extra) scope.setContext("extra", extra);
    Sentry.captureException(err);
  });
}
