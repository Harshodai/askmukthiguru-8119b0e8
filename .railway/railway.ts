import { defineRailway, project, service } from "railway/iac";

// This repository manages only its own resources in the environment.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "askmukthiguru-8119b0e8";

export default defineRailway(() => {
  // ── Backend API Service ──────────────────────────────────────────────────
  // Multi-stage Dockerfile (builder + runtime). Target ~2.5GB image (was 7.8GB).
  // QUANTIZED_ONLY=true: INT8 ONNX models only at build time.
  // healthcheckTimeout 330s: Railway retries healthz for up to 330s on deploy.
  // _GRACE_SECONDS=180: start_railway.py returns 200 unconditionally for 180s
  //   to allow model warm-up. Between 180s and 330s healthz returns 503 ("not ready").
  //   The two must NOT be equal — see backend/tests/test_healthz_grace_masking.py.
  const askmukthiguru_8119b0e8 = service("askmukthiguru-8119b0e8", {
    start: "python start_railway.py",
    healthcheck: "/api/healthz",
    healthcheckTimeout: 330,
    // Dockerfile settings (must be kept in sync with Railway service settings UI)
    // dockerfilePath: "backend/Dockerfile.railway"
    // builder: "DOCKERFILE"
    // watchPatterns: ["backend/**", "memory/**", ".railway/**", "backend/Dockerfile.railway"]
  });

  return project("resilient-embrace", {
    resources: [askmukthiguru_8119b0e8],
  });
});
