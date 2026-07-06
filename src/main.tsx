import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { RootErrorBoundary } from "./components/common/RootErrorBoundary";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <RootErrorBoundary>
    <App />
  </RootErrorBoundary>
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
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    window.location.reload();
  });

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => console.log("[MukthiGuru] SW registered:", reg.scope))
      .catch((err) => console.warn("[MukthiGuru] SW registration skipped:", err?.message ?? err));
  });
}
