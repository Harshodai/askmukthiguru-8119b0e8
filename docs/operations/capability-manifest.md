# Capability manifest gate

`GET /api/capabilities` is the backend’s public, secret-free statement of what this deployment can honestly offer. It distinguishes **available**, **unavailable** (enabled policy but missing runtime dependency), and **disabled by policy**.

The web chat reads that manifest at startup. Server-dependent composer actions are removed when their capability is explicitly unavailable or disabled. The browser retains working local actions when the manifest cannot be fetched, so a temporary backend-health failure does not create a newly dead button in an otherwise usable client.

| Composer action | Manifest key | Authority |
|---|---|---|
| Serene Mind | `serene_mind` | Backend service availability. |
| Guided meditation | `guided_meditation` | Bundled client flow. |
| Text attachment | `text_attachments` | Browser-local text ingestion path. |
| Voice input | `voice_input` | Browser capability; the existing browser support check remains authoritative. |

The manifest must never advertise model identity, API keys, provider account state, internal endpoint URLs, user data, or content. Any new visible action must add a capability key and an automated assertion before its control is released.
