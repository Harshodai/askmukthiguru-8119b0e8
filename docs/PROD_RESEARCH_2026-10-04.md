# Product Research & Kill List — 2026-10-04

**Purpose.** Owner asked: "research more ruthlessly to kill all things and make this a better and best product."
**Owner constraints (answered 2026-10-04):** official/inside the Oneness–Ekam foundation · free + donations · infra ≤ $35/mo · all seekers/beginners/mother-tongue users · all markets (Telugu, Hindi, English, multi-Indic) · north star = everything ("we missed most things").

**Method.** 4 parallel search waves (30+ queries) + App Store page fetch. Every number below is sourced; speculation is labeled ⚠.

---

## 1. Market facts

| Fact | Number | Source |
|---|---|---|
| Spiritual wellness apps market | $2.5B (2025) → $2.8B (2026) → $7.4B (2033), **14.8% CAGR** | Grand View Research |
| Segment mix (2025) | Paid IAP **62.8%** of revenue, but **free is fastest-growing** segment | Grand View Research |
| Platform mix | Android **47.6%**, iOS fastest-growing, web 25% | Grand View / Towards Healthcare |
| Faith-based apps slice | ~10% of spiritual wellness apps | Towards Healthcare (14.66% CAGR to 2035) |
| Weekly ChatGPT users | ~900M; only ~10% of ChatGPT citations overlap Google top-10 | Yotpo GEO guide |
| India voice behavior | ~70% of India talks rather than types; 55% of voice users rural | Awaaz.ai / LinkedIn India tech |
| Wellness D30 retention | Calm **5.2%**, Headspace **4.7%**, industry avg ~5.6–8.5%, Insight Timer **16%** (community) | StriveCloud / Apptopia |

**Read:** category is growing fast, free tier is where growth is, Android is the Indian battlefield, and *nobody in wellness has cracked D30 except via community or ritual*.

---

## 2. Competitor teardown (what to steal / what kills us)

### Direct — AI spiritual Q&A
| Comp | Evidence | Steal | Weakness we exploit |
|---|---|---|---|
| **GitaGPT** (2023, Google eng.) | 100K users in days; 5 clones within 2 months; **backlash** over "killing for dharma is justified" answer; "Rise and Failure of GitaGPT" post-mortems | Speed of launch, Krishna-persona demand | Trust destroyed by hallucination. **Our verbatim + abstention + zero-citation honesty is the anti-GitaGPT story.** |
| **AskYourGuide.ai** | Ships "Chatmate": WhatsApp bot answering "in Gurudev's own voice and idiom, Hindi + English, 3 AM" — direct model copy | **WhatsApp channel + voice/idiom framing** | No evidence of scale; multi-guru (not inside one foundation) |
| **Hue Learn / Innerverse 360** | Nonprofit, Bengaluru, in AP's Aug-2026 guru-chatbot story | Nonprofit angle | Fragmented content, not a living-teacher archive |
| **ISKCON-approved srimadgita.com** | 75K users, 4.8★ (1,567 ratings), "authenticity" as brand | "Approved by the tradition" badge | Scripture-only, English-centric |
| **Delphi.ai** | Mind-clone SaaS, $97–497/mo, video avatars | Licensing playbook for teacher clones | Hosts *generic* clones; no faith-safety rails; teacher must self-host data |
| **Sadhguru / Krishna-hologram / digital-avatars** | AP Aug-2026: gurus launching lifelike chatbots; Gulf News: "gurus launch digital avatars" | The press wave is **now** | Most avatars are persona-deepfake, not corpus-grounded |

### Adjacent — retention & distribution machines
| Comp | Evidence | Steal |
|---|---|---|
| **Sri Mandir (AppsForBharat)** | $33.4M raised, **40M downloads, 3.5M MAU, ~55% 6-month retention**, adding AI faith-Q&A + WhatsApp bot | **Recurring ritual transactions** = the only proven 55% retention lever in India devotion |
| **Hallow** (Catholic) | 23M downloads, ~$759M valuation (reported), ~$900K/mo revenue, 1B+ prayers; free + sub | **Streaks, routines, timed reminder notifications, 40-day challenge events** (Lent events drive store peaks) |
| **Medito Foundation** | Nonprofit, **4.1M users / 190 countries, free forever**, funded by donations + grants + volunteers | **The exact free+donations proof point** — our model is validated |
| **Insight Timer** | 16% D30 via **community** (groups, local meetups, leaderboards) | Community feature = the only D30 doubler |
| **Drik Panchang** | 4.8★, **210,746 ratings** — tithi/vrat/festival reminders | Panchang/festival reminder = India's daily-ritual utility; we have **zero** of this |

---

## 3. Our foundation's own footprint (the positioning truth)

| Asset | State |
|---|---|
| **Ekam-Oneness app** (iOS, OWA Holdings, © 2025) | Meditations + courses, **subscription paywall**, English + 8 languages, **no ratings yet** (weak traction), **no AI/ask feature** |
| ekam.org "Everyday at Ekam" | Free meditations |
| YouTube @theonenessmovement | 92.8K subs, 1.4K videos |
| Instagram | ~104K |
| **AskMukthiGuru** | Live on `askmukthiguru.lovable.app`, indexed (guides/practices pages), **lovable.app subdomain = borrowed domain**, **no app-store presence**, no link-in-bio funnel evidence, no donation rail, no WhatsApp, no panchang, no streaks, no community |

⚠ Two official apps coexist: paywalled meditation courses (OWA) vs free AI companion (us). **Strategic question for the foundation: one app or a free-funnel + paid-premium ladder?** Recommendation in §4.

---

## 4. KILL LIST — ranked gaps (the "we missed most things" answer)

### P0 — kills us within a year if unfixed
1. **Budget vs reality.** Owner ceiling $35/mo. Railway usage $28.79 with **$53.84 estimate vs $30 hard limit** (94% memory). → Memory/cost optimization is not optional, it's the gating item before Ask 8 (already the standing rule). *Target: full stack ≤ $30/mo with headroom.*
2. **No retention engine.** Chat-only products die at D30 ≤5%. Missing: **streak (daily practice completion), timed reminders, daily ritual unit ("10-min morning with the teachers"), panchang/festival/vrat calendar** (Drik Panchang = 210K ratings proves demand). Push infra exists (`backend/app/api/push.py`, FCM/APNs) but is not wired to any ritual.
3. **Latency.** Production 14.6–31.4s pipeline vs instant-chat expectation (Hallow = instant audio). Chat UX that takes 30s loses the 3 AM seeker. → Existing Phase-1 latency gates + canary (p50 ≤1660ms) remain the core engineering KPI.
4. **Trust story not public.** GitaGPT was *destroyed* by one hallucinated answer; BBC/AP are running "AI + gurus" stories **right now** (Aug–Oct 2026). Our differentiator — verbatim living-teacher voice, abstention, zero-citation honesty, safety rails — has **no public-facing trust page**. This is the press hook.

### P1 — growth ceiling without these
5. **No India distribution channel.** Sri Mandir + AskYourGuide + Hindu Pray all build on **WhatsApp**. We have none. Voice-first (STT/TTS per locale already exists) maps to "70% of India talks, doesn't type".
6. **No app store presence / Android missing.** Android = 47.6% of the category. Capacitor wrapper **already built** (`npm run cap:sync`). Path: Play Store first (India), iOS later. Or — embed AskMukthiGuru as the **AI layer inside the Ekam-Oneness app** (owner is inside the foundation; that's a one-decision distribution win with 0 ASO cost).
7. **Donation rail missing.** Medito proves donations+grants funds 4.1M users. Mechanics: **Razorpay NGO gateway (UPI, payment pages, UPI AutoPay recurring, 80G receipts)**; Play Store donation links require tax-exempt proof (Indian 80G trust docs — foundation almost certainly has them ⚠ verify); Apple donations need nonprofit approval. Web checkout first (free of store 30% + policy risk).
8. **Audience not funneled.** 92.8K YT + 104K IG + ekam.org → AskMukthiGuru link nowhere (no evidence). Free tool is the perfect link-in-bio / video CTA.
9. **GEO invisible.** 900M weekly ChatGPT users cite only ~10% of Google's top-10; stats + citations + quotes lift AI-visibility ~40%. "Ask Preethaji teachings" should be *the* citable source. We have SEO skills in-repo; no GEO plan.

### P2 — moat builders
10. **Community/satsang layer** (Insight Timer's 16% D30 driver): shared reflections, group challenges, local circles — v2, needs moderation design.
11. **Offline blessing** (ET: spiritual apps succeed offline): downloadable meditation + cached teachings for low-connectivity India.
12. **Public trust page**: "How this AI answers" — verbatim policy, abstention examples, safety policy, sources. Cheap, differentiating, quotable by press.

### Positioning decision (recommendation)
**Free AI companion = top of funnel; Ekam-Oneness paid app = depth.** Free+donaions validated by Medito; paywalled courses validated by Ekam's own app; our AI becomes the acquisition engine for both. One foundation, two rungs, WhatsApp + YouTube + store share the funnel.

---

## 5. 30-day MVP cut (aligned with standing Phase 1 gates)

| # | Action | Cost | Depends on |
|---|---|---|---|
| 1 | Finish ingest + Phase 1 gates (quality floor first) | $0 | PID 18500 running |
| 2 | Memory/cost optimization → ≤$30/mo measured | $0 | parallel-safe |
| 3 | Daily ritual: streak + one reminder + "today's teaching" | $0 | push infra exists |
| 4 | Panchang/festival calendar (data: Drik open data or panchang API) | $0–10 | — |
| 5 | WhatsApp bot MVP (Meta Cloud API free tier) | $0 | after latency <10s |
| 6 | Donation page (Razorpay, 80G receipt) | setup free | foundation 80G ⚠ |
| 7 | Play Store build via existing Capacitor | $25 one-time dev fee | Phase 1 green + consent |
| 8 | Trust page + GEO content pass on /guides | $0 | — |
| 9 | Decide: own domain (askmukthiguru.com) vs lovable.app | ~$12/yr | — |
| 10 | YouTube/IG CTA wiring (link-in-bio → free tool) | $0 | foundation social accounts |

**Budget check:** items above ≈ $0–35/mo total, fits ceiling. Foundation's existing app/socials carry distribution.

---

## 6. Sources (key)

- Grand View Research — Spiritual Wellness Apps Market (2026–2033), updated Aug 2026
- TechCrunch 2025-06-30 — Sri Mandir investor traction (40M downloads, retention)
- Contrary Research — Hallow business breakdown; Sensor Tower figures via press
- Medito Foundation — about/free-app pages (4.1M users, donation funding)
- StriveCloud/Apptopia — Insight Timer 16% D30 vs Calm/Headspace ~8.5%
- AP News 2026-08-28 — "Gurus roll out chatbots" (Sadhguru chatbot, Hue Learn)
- BBC Future 2025-10-16 — "People are using AI to talk to God" (GitaGPT backlash)
- askyourguide.ai — Chatmate WhatsApp guru bot
- Apple App Store — Ekam-Oneness listing (OWA Holdings, subscription, no ratings)
- Drik Panchang — Play Store 4.8★/210,746
- Google Play Developer policy — donation eligibility (tax-exempt proof)
- Razorpay — NGO donation gateway (UPI AutoPay, 80G)
- Yotpo — ChatGPT SEO/GEO 2026 (citation overlap, +40% tactics)
- Awaaz.ai / India voice-market reports — vernacular voice-first adoption
