import {
  defineRailway,
  github,
  preserve,
  project,
  redis,
  service,
} from "railway/iac";

// Infrastructure as Code for Railway staging and production (T9-01, RW-05).
//
// THIS FILE IS NOT APPLIED BY ANY SCRIPT OR WORKFLOW. Railway does not read
// `.railway/` during deploys; a merged change does nothing until the owner runs
//   railway config plan --out railway-plan.json
//   railway config apply --plan railway-plan.json --yes
// (docs.railway.com/infrastructure-as-code). Read the plan first: it must not
// contain a destructive change. Gate A item A1 needs that plan saved.
//
// What the syntax check covers. `defineRailway`, `service`, `github`,
// `preserve`, `redis`, `project`, `ctx.environment`, `env`, `replicas`,
// `healthcheck`, `healthcheckTimeout` and `source` appear in Railway's IaC
// reference examples (checked 2026-11-06). The reference does not list a
// Dockerfile path, restart policy, drain time, resource limits, or Wait for CI,
// so those are variables or dashboard settings, listed at the end of this file.
//
// Spec: audits/audit-output-2026-11-04/specifications/
//       RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md sections 5-8.

// This repository manages only its own resources in the environment.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "askmukthiguru-8119b0e8";

// ---- Owner decisions that gate parts of this file -------------------------
//
// Owner decisions 2026-11-20/21: repository production posture is v13_shadow
// (first_person_v13_shadow), promoted from v12 on 2026-11-21 after corpus-gap
// teachings were added. Relevance min score 2, scorer anthropic/claude-haiku-5.5,
// answerability gate on. Single source: PRODUCTION_POSTURE in
// backend/services/first_person_serving_contract.py (drift guard:
// backend/tests/test_production_posture_drift_2026_11_20.py).
// History, D-14 decided 2026-11-07: v10-only; v12_shadow remains selectable as a
// prior baseline. The posture is read back from the "Serving posture:" startup
// log line (backend/app/main.py). "v8_bridge" stays as the rollback value.
// The checked-in IaC is intended configuration, not proof of the live Railway
// environment; verify the deployed service's startup log before claiming parity.
// test_railway_iac.py pins this.
type ServingPosture = "unset" | "v10_only" | "v12_shadow" | "v13_shadow" | "v8_bridge";
const SERVING_POSTURE: ServingPosture = "v13_shadow";

// D-30 decided 2026-11-07: worker and beat are ON in staging. This is the one
// switch: set it to false to drop both services from the plan.
const INCLUDE_CELERY = true;

// D-26 decided 2026-11-07: Qdrant is external. It is NOT a Railway service here.
// The backend and worker read QDRANT_URL and the read-only key from the
// environment (preserve(): set both in the dashboard). Never put the write key
// on a Railway service (backend/app/config.py: the running backend never gets it).
//
// Faculty reviewers sign in with Google like any user (owner decision 2026-11-28);
// there is no shared access-code gate.

const REPO = "Harshodai/askmukthiguru-8119b0e8";

// The Dockerfile is not named `Dockerfile`, so Railway needs this variable to
// find it. `service()` has no Dockerfile option (F-4).
const DOCKERFILE_PATH = "backend/Dockerfile.railway";

// Railway's drain time defaults to 0 s, so the old deploy is SIGKILLed at once.
// backend/app/main.py waits up to 45 s for in-flight requests, so the backend
// and worker get 60 s. Beat holds no request state and gets 30 s.
// CELERY_SHUTDOWN_GRACE_SECONDS (backend/start_railway.py) must stay BELOW the
// drain time of the same service: 50 < 60 for the worker, 20 < 30 for beat.
const DRAIN_SECONDS_BACKEND = "60";
const DRAIN_SECONDS_WORKER = "60";
const DRAIN_SECONDS_BEAT = "30";

export default defineRailway((ctx) => {
  // Only the exact name "production" is production. Any other environment name
  // (for example "staging" or a PR environment) gets ENVIRONMENT=staging.
  const environmentName = ctx.environment === "production" ? "production" : "staging";

  // Variables every Python service needs, because worker and beat import
  // app.config and its startup validators (docker-compose.prod.yml, beat).
  // Secrets are preserve(): set them in the dashboard first. A sealed variable
  // is not copied into a duplicated environment, so set it once per environment.
  const sharedEnv = {
    RAILWAY_DOCKERFILE_PATH: DOCKERFILE_PATH,
    ENVIRONMENT: environmentName,
    JWT_SECRET: preserve(),
    ANON_SESSION_HMAC_SECRET: preserve(),
    BRAIN_KEK: preserve(),
    OPENROUTER_API_KEY: preserve(),
    SUPABASE_URL: preserve(),
    SUPABASE_KEY: preserve(),
    QDRANT_URL: preserve(), // D-26: external Qdrant, http://<host>:6333
    QDRANT_READ_ONLY_API_KEY: preserve(),
    // Spend controls. The guard is on and fails closed (config.py refuses a
    // production boot with it off). Caps are set per environment.
    OPENROUTER_BUDGET_GUARD_ENABLED: "true",
    OPENROUTER_BUDGET_FAIL_CLOSED: "true",
    OPENROUTER_DAILY_BUDGET_USD: preserve(),
    OPENROUTER_MONTHLY_BUDGET_USD: preserve(),
  };

  // ---- Redis -------------------------------------------------------------
  // Managed Redis template. It holds cache entries AND quota and rate-limit
  // counters, so its eviction policy must be `noeviction` (Gate A14). Redis's
  // own default is noeviction; `scripts/ops/railway_cleanup.py --tune-redis`
  // sets maxmemory 512mb and noeviction, and A14 checks it with
  // `CONFIG GET maxmemory-policy`. [INF] If A14 fails, replace this with an
  // image service that runs `redis-server ... --maxmemory-policy noeviction
  // --appendonly yes` (runbook section 5).
  const cache = redis("redis");

  // ---- Serving posture (D-14) ---------------------------------------------
  const postureEnv =
    SERVING_POSTURE === "v10_only"
      ? {
          FIRST_PERSON_ACTIVE_COLLECTION: "first_person_v10",
          FIRST_PERSON_COLLECTION: "first_person_v10",
          FIRST_PERSON_CONTEXT_COLLECTION: "first_person_v10",
          FIRST_PERSON_CONTEXT_HARNESS_ENABLED: "true",
          FIRST_PERSON_CONTEXT_TERMINAL_ENABLED: "true",
          FIRST_PERSON_SERVING_POSTURE: SERVING_POSTURE,
        }
      : SERVING_POSTURE === "v13_shadow"
        ? {
            // v13_shadow is the production posture (owner decision 2026-11-21).
            // Includes 13 newly segmented corpus gap teachings on top of v12 baseline.
            FIRST_PERSON_ACTIVE_COLLECTION: "first_person_v13_shadow",
            FIRST_PERSON_COLLECTION: "first_person_v13_shadow",
            FIRST_PERSON_CONTEXT_COLLECTION: "first_person_v13_shadow",
            FIRST_PERSON_CONTEXT_HARNESS_ENABLED: "true",
            FIRST_PERSON_CONTEXT_TERMINAL_ENABLED: "true",
            FIRST_PERSON_SERVING_POSTURE: SERVING_POSTURE,
          }
      : SERVING_POSTURE === "v12_shadow"
        ? {
            // v12_shadow is the production posture (owner decision 2026-11-20).
            // 1,996 topic_ids, 2× speaker-verified rate vs v10 (51.3% vs 26.5%).
            // Set FIRST_PERSON_REQUIRE_SPEAKER_VERIFIED=true (default) so only
            // the verified portion of v12 is served.
            FIRST_PERSON_ACTIVE_COLLECTION: "first_person_v12_shadow",
            FIRST_PERSON_COLLECTION: "first_person_v12_shadow",
            FIRST_PERSON_CONTEXT_COLLECTION: "first_person_v12_shadow",
            FIRST_PERSON_CONTEXT_HARNESS_ENABLED: "true",
            FIRST_PERSON_CONTEXT_TERMINAL_ENABLED: "true",
            FIRST_PERSON_SERVING_POSTURE: SERVING_POSTURE,
          }
        : SERVING_POSTURE === "v8_bridge"
        ? {
            // Harness flags stay at their false defaults, so the collection
            // resolves to first_person_v8 (config.py resolve_first_person_active_collection).
            FIRST_PERSON_CONTEXT_HARNESS_ENABLED: "false",
            FIRST_PERSON_CONTEXT_TERMINAL_ENABLED: "false",
            FIRST_PERSON_SERVING_POSTURE: SERVING_POSTURE,
          }
        : {
            FIRST_PERSON_ACTIVE_COLLECTION: preserve(),
            FIRST_PERSON_CONTEXT_HARNESS_ENABLED: preserve(),
            FIRST_PERSON_CONTEXT_TERMINAL_ENABLED: preserve(),
            FIRST_PERSON_SERVING_POSTURE: preserve(),
          };

  // ---- Live first-person-only posture (U2, 2026-11-16) -------------------------
  // Railway gets code defaults for any variable not pinned, and these differ from
  // the live local values. Non-secret literals only. Pinned on backend AND worker
  // (both import app.config). Guard: tests/test_railway_posture_pinned_2026_11_16.py.
  const livePosture = {
    FIRST_PERSON_CHAT_BRIDGE_ENABLED: "true",
    FIRST_PERSON_LLM_FALLBACK_ENABLED: "false",
    FIRST_PERSON_SERVE_WEAK_MATCH: "true",
    FIRST_PERSON_REQUIRE_SPEAKER_VERIFIED: "true",
    // Owner decision 2026-11-20: production min score 2 (min 3 abstained on ~85% of
    // questions, docs/handoffs/LOOP_NOTES_2026_11_20.md "LEAD CORRECTION"). The code
    // default in config.py is 3 and docker-compose.graded.yml pins its own frozen 3.
    FIRST_PERSON_RELEVANCE_MIN_SCORE: "2",
    FIRST_PERSON_RELEVANCE_MODEL: "anthropic/claude-haiku-5.5",
    DISTRESS_LLM_ESCALATION_ENABLED: "true",
    FIRST_PERSON_CONTEXT_USE_SPARSE: "false",
    FIRST_PERSON_LLM_RERANK_ENABLED: "false",
    SEMANTIC_CACHE_ENABLED: "false",
    WEB_SEARCH_ENABLED: "false",
    FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED: "true",
    FIRST_PERSON_HYDE_ENABLED: "true",
  };

  // ---- Backend API ---------------------------------------------------------
  // Multi-stage Dockerfile (builder + runtime). QUANTIZED_ONLY=true: INT8 ONNX
  // models only at build time.
  // healthcheckTimeout 330 s: Railway retries /api/healthz for up to 330 s on
  //   deploy. start_railway.py returns 200 unconditionally for _GRACE_SECONDS
  //   (180) while models warm up; from 180 s to 330 s it returns 503 "not
  //   ready". The two must NOT be equal (test_healthz_grace_masking.py).
  // Source is the GitHub repository, so Railway sets RAILWAY_GIT_COMMIT_SHA on
  //   each deploy. The first-person production contract needs a concrete git
  //   SHA (backend/services/first_person_release.py); a `railway up` deploy sets
  //   none, which is why scripts/deploy/deploy_railway.sh also sets GIT_SHA.
  const backend = service("askmukthiguru-8119b0e8", {
    source: github(REPO),
    start: "python start_railway.py",
    healthcheck: "/api/healthz",
    healthcheckTimeout: 330,
    replicas: 1, // chat admission caps are per process; replicas multiply them
    env: {
      ...sharedEnv,
      ...postureEnv,
      ...livePosture,
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: DRAIN_SECONDS_BACKEND,
      REDIS_URL: cache.env.REDIS_URL,
      METRICS_SCRAPE_TOKEN: preserve(),
      CORS_ORIGINS: preserve(), // exact origins only, no "*"
      ALLOWED_HOSTS: preserve(),
      FORWARDED_ALLOW_IPS: "10.0.0.0/8",
      WEB_CONCURRENCY: "1",
      PYTHON_MEMORY_LIMIT_MB: "0",
      OPENROUTER_EXTRA_ALLOWED_MODELS: preserve(),
    },
  });

  // ---- Celery worker -----------------------------------------------------
  // start_railway.py serves /api/healthz on PORT for this mode and forwards
  // SIGTERM to Celery (NEW-RW-3). The `memory` queue runs the memory outbox
  // drain; without it consent behaviour (T1-10) does not run.
  const worker = service("celery-worker", {
    source: github(REPO),
    start: "python start_railway.py",
    healthcheck: "/api/healthz",
    healthcheckTimeout: 120,
    replicas: 1,
    env: {
      ...sharedEnv,
      ...postureEnv,
      ...livePosture,
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: DRAIN_SECONDS_WORKER,
      SERVICE_TYPE: "celery",
      CELERY_QUEUES: "ingestion,embedding,indexing,okf,memory",
      CELERY_CONCURRENCY: "1",
      CELERY_SHUTDOWN_GRACE_SECONDS: "50",
      REDIS_URL: cache.env.REDIS_URL,
    },
  });

  // ---- Celery beat: exactly one instance ---------------------------------
  // Two beats double every scheduled task. Never raise replicas. Railway cron
  // is not a substitute: cron jobs must exit, beat is a long-running process.
  // Beat serves no HTTP, so it has no healthcheck.
  const beat = service("celery-beat", {
    source: github(REPO),
    start: "python start_railway.py",
    replicas: 1,
    env: {
      ...sharedEnv,
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: DRAIN_SECONDS_BEAT,
      SERVICE_TYPE: "celery-beat",
      CELERY_SHUTDOWN_GRACE_SECONDS: "20",
      REDIS_URL: cache.env.REDIS_URL,
    },
  });

  const celery = INCLUDE_CELERY ? [worker, beat] : [];

  return project("resilient-embrace", { resources: [cache, backend, ...celery] });
});

// ---- Settings that are NOT in this file (dashboard, per environment) -------
// Record each one in the release evidence (Gate A19).
//  - Wait for CI: on each GitHub-triggered service, so a failed workflow skips
//    the deploy (docs.railway.com/deployments/github-autodeploys).
//  - Branch: the branch each service deploys from.
//  - Restart policy: On Failure, the default (10 restarts).
//  - Memory and CPU limits per service.
//  - Usage limit and alert (a hard limit takes every workload offline).
//  - Public domain: the generated Railway domain is enough for staging.
//  - Variable `REDIS_URL` is wired from the Redis service; if `cache.env.REDIS_URL`
//    is not the name the template exposes, `railway config plan` fails and the
//    name must be corrected from `railway variables --service redis`. [INF]
