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
// Skip in preview / iframe environments where /sw.js is served behind a redirect
// (browsers block SW registration when the script response is a redirect).
const isPreviewIframe =
  typeof window !== "undefined" &&
  (window.location.hostname.endsWith(".lovableproject.com") ||
    window.location.hostname.endsWith(".lovable.app") === false ||
    window.self !== window.top);

if ("serviceWorker" in navigator && !isPreviewIframe) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => console.log("[MukthiGuru] SW registered:", reg.scope))
      .catch((err) => console.warn("[MukthiGuru] SW registration skipped:", err?.message ?? err));
  });
}
