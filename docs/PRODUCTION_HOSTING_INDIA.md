# Production Hosting — India-First, Lowest Cost (2026)

**Decision frame:** Mukthi Guru has two halves.

1. **Frontend + auth + DB + edge functions + storage** — already on Lovable Cloud (Supabase under the hood, ap-south-1/Mumbai region available). Zero ops, ~$0–25/mo until ~10k MAU. **Recommendation: keep.**
2. **Heavy backend** — FastAPI + Qdrant + Redis + Neo4j + Sarvam 30B on Ollama. This is the part that needs an India-resident VPS or GPU box.

This doc covers part 2 only.

## Constraints recap

- Indian end-users → need ≤ 50 ms RTT to Mumbai/Chennai/Bangalore.
- $0–$50/mo budget for the FastAPI + retrieval stack (no GPU).
- LLM inference: prefer a paid API (Sarvam, Krutrim, Groq) over self-hosted GPUs — a 24 GB GPU box in India is ≥ ₹15k/mo and idle 95% of the time at our scale.

## CPU/RAM hosting comparison (India-resident, INR list, 2026)

| Provider | Region | 2 vCPU / 4 GB | 4 vCPU / 8 GB | Notes |
| --- | --- | ---: | ---: | --- |
| **Hetzner CAX21 (ARM)** | EU only (Falkenstein/Helsinki/Ashburn) | — | — | Cheapest globally but **no India PoP** → ~180 ms RTT to Mumbai. Use **Cloudflare → cache + tunnel** to mask; still bad for streaming SSE. ❌ for primary. |
| **Inservers IN-BASIC (AMD EPYC 7C13)** | Mumbai (Yotta) | ₹880/mo | ₹1 600/mo | Cheapest dedicated-vCPU India VPS. INR billing, GST invoice. Good for FastAPI + Qdrant local. ✅ |
| **GigaNodes / GBNodes** | Noida | ₹990/mo | ₹1 850/mo | Yotta DC, similar tier. |
| **Hetzner Cloud + CF India** | DE + CF Mumbai PoP | €4.5/mo (~₹420) | €7.5/mo (~₹700) | Cheapest absolute, **but** origin in EU; static/cached assets fast via CF, dynamic SSE will feel ~150 ms slower per token. |
| **AWS Lightsail Mumbai** | ap-south-1 | $5/mo (~₹430) | $12/mo (~₹1 030) | Mature, IPv6, snapshots; bandwidth 2 TB included. Good middle ground if you prefer USD billing + hyperscaler. ✅ |
| **DigitalOcean Bangalore** | BLR1 | $6/mo | $12/mo | Same shape as Lightsail; better dashboards. |
| **E2E Networks C2.4GB.20** | NCR/Mumbai/Chennai | ₹944/mo | ₹1 888/mo | MeitY-empaneled, INR, GST. Best if you need future GPU burst (A100 ₹185/hr on-demand). |
| **AWS EC2 t4g.small** | ap-south-1 | ~$11/mo | ~$22/mo | More expensive than Lightsail at the same shape. |

**Pick:** **Inservers IN-MID (4 vCPU / 8 GB / Mumbai, ₹1 600/mo ≈ $19)** as the primary FastAPI + Qdrant + Redis + Neo4j single box, with **AWS Lightsail Mumbai 4 GB ($12/mo)** as the hot-standby. Both behind a Cloudflare proxy with India-PoP routing — gives DDoS, WAF, and free SSL.

If you only want one provider: **AWS Lightsail Mumbai 4 GB ($12/mo)** — boring, dependable, hyperscaler, USD billing.

## LLM inference — the real cost driver

Self-hosting Sarvam 30B on Ollama needs a 24 GB GPU. Cheapest India options:

| Provider | GPU | Price | Notes |
| --- | --- | ---: | --- |
| E2E A100 40 GB on-demand | A100 | ~₹185/hr (~₹133 000/mo if 24×7) | Way over budget |
| RunPod community A100 | A100 | $0.79/hr (~₹47k/mo 24×7) | Cheaper but US/EU |
| Lambda Cloud | A100 | $1.29/hr | EU/US |

**Cheaper path: use a hosted India-friendly inference API.**

| API | Model class | Price (INR/1k input) | Price (INR/1k output) | India region | Verdict |
| --- | --- | ---: | ---: | --- | --- |
| **Sarvam M (Sarvam-1)** | 7B Indic | ~₹0.018 | ~₹0.036 | Mumbai | Best for Hindi/Telugu/Malayalam quality. Lovable AI Gateway already proxies it — no key needed. ✅ |
| **Krutrim Cloud (Krutrim-2)** | 70B-class | ~₹0.06 | ~₹0.18 | Bangalore | MeitY, INR, GST. Use as paid fallback. |
| **Groq Llama 3.3 70B** | 70B | $0.59/1M ≈ ₹0.049/1k | $0.79/1M ≈ ₹0.066/1k | US only — 200ms RTT | Cheap + 500 tok/s. Good for non-Indic. |
| **Google Gemini 2.5 Flash via Lovable AI Gateway** | Frontier | $0.075/1M ≈ ₹0.006/1k | $0.30/1M ≈ ₹0.025/1k | Global, low India latency | **Cheapest frontier-quality**. Already wired in this project. ✅ |
| **Lovable AI Gateway default (gemini-2.5-flash)** | — | included in Cloud free tier until first 10M tokens | — | — | Use until billing kicks in |

**Recommendation:** route by language — Indic queries → `sarvam-m` (via gateway), everything else → `google/gemini-2.5-flash` (via gateway). Skip self-hosted Sarvam 30B in prod; keep it as a local-dev fallback.

## Recommended production architecture (cheapest)

```
                ┌─────────────────────────┐
   Users (IN)──►│ Cloudflare (free plan)  │  ← WAF, DDoS, SSL, India PoP
                └─────────┬───────────────┘
                          │
       ┌──────────────────┼─────────────────────────────┐
       │                  │                             │
       ▼                  ▼                             ▼
 askmukthiguru     api.askmukthiguru             *.functions
 .lovable.app      .com (Lightsail Mumbai)       .supabase.co
 (Lovable Cloud)        FastAPI                  (healthz, push-send,
   = SPA + auth         + Qdrant local            chat-rate-limit,
   + DB (ap-south-1)    + Redis                   ai-chat, sarvam-stt/tts)
   + storage            + Neo4j (single-node)
                        + Whisper local
                                │
                                ▼
                   Lovable AI Gateway ──► Gemini 2.5 Flash / Sarvam M
                                          (no self-hosted LLM)
```

## Cost rollup (monthly, INR, 10k MAU / 200k chat turns)

| Item | Cost |
| --- | ---: |
| Lovable Cloud (Supabase ap-south-1, Pro tier when free runs out) | ₹2 100 |
| AWS Lightsail Mumbai 4 GB (FastAPI + Qdrant + Redis + Neo4j) | ₹1 030 |
| Cloudflare Free | ₹0 |
| Domain (.com via Cloudflare Registrar) | ₹85 |
| LLM via gateway (200k turns × ~500 in + 300 out tokens, ~70% gemini-flash + 30% sarvam-m) | ~₹3 500 |
| STT/TTS (Sarvam pay-as-you-go, ~10% of users) | ~₹600 |
| **Total** | **~₹7 300 / mo (~$87)** |

## Step-by-step deploy (Lightsail Mumbai)

```bash
# 1. Create instance — Lightsail console → Mumbai → Ubuntu 22.04 → 4 GB plan → name "mukthiguru-api".
# 2. Attach static IP, open ports 80/443/8000 in firewall.
# 3. SSH in:
ssh -i LightsailKey.pem ubuntu@<static-ip>
sudo apt update && sudo apt -y install docker.io docker-compose-v2 nginx certbot python3-certbot-nginx git
sudo usermod -aG docker $USER && newgrp docker

# 4. Clone + boot
git clone https://github.com/<you>/mukthiguru.git && cd mukthiguru/backend
cp .env.example .env   # fill secrets — SUPABASE_URL, SUPABASE_KEY, LOVABLE_API_KEY, SARVAM_API_KEY
docker compose up -d --build

# 5. Reverse proxy
sudo tee /etc/nginx/sites-available/api <<'NGX'
server {
  server_name api.askmukthiguru.com;
  client_max_body_size 25M;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host;
               proxy_set_header X-Forwarded-For $remote_addr;
               proxy_read_timeout 120s; proxy_buffering off; }   # buffering off = SSE friendly
}
NGX
sudo ln -s /etc/nginx/sites-available/api /etc/nginx/sites-enabled/
sudo certbot --nginx -d api.askmukthiguru.com
sudo systemctl reload nginx

# 6. Point DNS — Cloudflare → A record `api` → static IP, proxy ON (orange cloud).

# 7. Frontend env (Lovable dashboard → secrets):
#     VITE_BACKEND_URL=https://api.askmukthiguru.com
```

## Operational tips

- **Backups:** Lightsail auto-snapshot (₹40/mo for 4 GB) + `scripts/ops/backup_qdrant.py` weekly to a Supabase storage bucket.
- **Monitoring:** point UptimeRobot (free 50 monitors) at `/healthz`, `/api/health`, `/api/chat` synthetic.
- **Cost guardrail:** Cloudflare WAF rule — block any IP doing > 60 req/min on `/api/chat`. Token bucket in edge function is the second layer.
- **Compliance:** Lightsail Mumbai is ap-south-1; data resident in India satisfies most DPDP requirements. Add a DPA in your privacy policy.

## Alternatives by goal

| Goal | Pick |
| --- | --- |
| Absolute cheapest, latency tolerated | Hetzner CX22 EU + Cloudflare ~$5/mo |
| INR billing + GST invoice | Inservers IN-MID or E2E C2 |
| Hyperscaler dependability | AWS Lightsail Mumbai 4 GB |
| Future GPU burst | E2E Networks (A100 on-demand by hour) |
| Fully managed, near-zero ops | Render / Railway (no India region — adds ~120 ms) |
