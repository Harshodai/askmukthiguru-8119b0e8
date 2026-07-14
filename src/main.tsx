import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { RootErrorBoundary } from "./components/common/RootErrorBoundary";
import { I18nextProvider } from "react-i18next";
import i18n from "./i18n";
import { initSentry } from "./lib/sentry";
import { initWebVitals } from "./lib/webVitals";
import "./index.css";

initSentry();
initWebVitals();

// Suppress extension-injected script errors and message port disconnect warnings.
// "Message port closed before a response was received" or "unhandled rejection"
// from message channel comes from browser extensions (Grammarly, Honey, etc.).
if (typeof window !== "undefined") {
  const handleExtensionError = (msg: string, source?: string) => {
    const isExtension = 
      (typeof source === "string" && source.includes("chrome-extension://")) ||
      (typeof msg === "string" && (
        msg.includes("message port closed") ||
        msg.includes("message channel closed") ||
        msg.includes("Extension context")
      ));
    return isExtension;
  };

  window.addEventListener("error", (event) => {
    if (handleExtensionError(event.message, event.filename)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason?.message || String(event.reason || "");
    if (handleExtensionError(reason)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
}

createRoot(document.getElementById("root")!).render(
  <I18nextProvider i18n={i18n}>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </I18nextProvider>
);

// Register service worker for offline asset caching and crisis pages availability.
// Skip on the Lovable preview origin and inside iframes — there /sw.js is served
// behind a redirect, which browsers reject for SW registration.
const canRegisterSW = (() => {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return false;
  try {
    if (window.self !== window.top) return false; // inside an iframe
  } catch {
    return false; // cross-origin frame → assume preview
  }
  const host = window.location.hostname;
  if (host.endsWith(".lovableproject.com")) return false; // preview sandbox
  return true;
})();

if (canRegisterSW) {
  // Reload once a new SW takes control of this tab, so an already-open tab
  // never keeps running against assets a fresh deploy has already removed.
  // Guard: skip reload on first install (controller was null at attach time).
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController) window.location.reload();
  });

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => console.log("[MukthiGuru] SW registered:", reg.scope))
      .catch((err) => console.warn("[MukthiGuru] SW registration skipped:", err?.message ?? err));
  });
}
