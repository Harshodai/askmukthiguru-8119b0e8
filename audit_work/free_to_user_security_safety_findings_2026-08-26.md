# Free-to-User Audit — Security, Privacy, Safety, and Rights Findings

**Evidence posture:** This is a static/repository reconciliation plus a limited read-only runtime probe. It does not claim a complete penetration test, authenticated E2E, production RLS proof, or external rights clearance.

## Verified controls

| Control | Evidence | Assessment |
|---|---|---|
| Signed anonymous-session contract | Auth route returns a signed token; chat resolves anonymous identity from the token rather than trusting a derived `anon:<id>` string | Strong design; runtime state-changing proof intentionally not performed in this audit phase |
| Anonymous quota | Admission-time atomic reservation, claim on success, release on failure/cancellation; Redis-first with conservative degraded in-memory limit | Real free-user abuse/cost control |
| Chat backpressure | Per-replica `max_concurrent_chat` semaphore rejects overload with HTTP 503 and `Retry-After` | Protects availability and provider spend from thundering-herd work |
| Admin protection | Admin routes depend on AAL2 and apply an optional `ADMIN_USER_IDS` allowlist | Defense in depth; requires deployment configuration verification |
| Tenant/session isolation | Session IDs are validated; anonymous history is kept separate; Second Brain rejects anonymous users and uses user-scoped storage | Strong repository evidence; cross-user runtime proof remains a separate test gate |
| Public SSE projection | Direct/queued SSE use explicit public projections; private memory, attachment, prompt, safety, and arbitrary graph state are excluded | Important privacy boundary; retain regression coverage whenever schemas change |
| Attachment isolation | Bounded byte/context limits, MIME sniffing, bounded OOXML/PDF/media extraction, temporary cleanup, untrusted-evidence fence, ephemeral metadata | Good baseline for free-user abuse resistance; malware scanning and durable artifact lifecycle remain open |
| Distress handling | Deterministic acute distress routes are fail-closed and separate from doctrine phrase overrides; output moderation is distinguished from system error | Safety-critical; latency optimization must not alter this ordering |
| Content-rights hygiene | Sensitive PDF/debug/cookie artifacts were removed from repository history and `.dockerignore` guards exist | Remaining uncertainty: derived vector/graph data and external source rights require explicit provenance audit |

## P0/P1 unresolved risks

1. **Runtime/source mismatch:** the local Uvicorn process on port 8001 does not expose `/api/capabilities` in its OpenAPI document even though the attached source mounts that router. Runtime claims must identify the exact process build and checkout; restart/reconciliation requires separate authorization.
2. **Readiness is not feature availability:** `/api/healthz` returned alive while `/api/health` returned `ready=false,status=unhealthy`, with embedding and LightRAG unavailable in the inspected process. A free user can encounter a live-looking but non-functional product unless frontend/API readiness messaging is explicit.
3. **Content-rights residue:** repository deletion does not prove that derived embeddings, graph nodes, caches, backups, or external copies have been removed or have a valid rights basis. Do not re-ingest or advertise rights-sensitive material without a source-level rights ledger and deletion verification.
4. **Free-user spend enforcement:** OpenRouter daily/monthly budgets and a per-request ceiling exist, but the shared budget guard is disabled by default. Soft alerts in `CostTracker` cannot prevent provider spend. Enabling a hard guard needs a Redis health/failure drill and an explicit deployment approval; no setting was changed here.
5. **Authenticated and cross-tenant proofs remain open:** Static dependencies show the intended gates, but no state-changing authenticated workflow, RLS cross-user probe, OAuth, password-reset, Second Brain, or memory-deletion run was executed under this audit brief.

## Safety and privacy rules for the next phases

No cost reduction may bypass distress detection, citations, evidence gates, user consent, tenant filtering, deletion semantics, or public SSE allowlists. Any deterministic shortcut must be restricted to a reviewed safe class, and any provider fallback must preserve `system_error` versus `abstained` semantics. Any free-tier quota or spend guard must fail conservatively without leaking session, memory, prompt, attachment, or provider details to public responses.
