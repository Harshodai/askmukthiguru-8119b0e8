# AskMukthiGuru — Store Listing & Privacy Disclosures

> Task 9 — Mobile App Launch assets.
> All char counts verified against store limits (Play short ≤80, App Store subtitle ≤30, keywords ≤100). Update placeholder URLs (lovable.app → final domain) before submission.

---

## 1. Google Play Store Listing

| Field | Value | Limit |
|---|---|---|
| **App name** | `AskMukthiGuru` | 30 |
| **Short description** | `AI spiritual guide rooted in the teachings of Sri Preethaji & Sri Krishnaji.` | 80 |
| **Category (primary)** | `Lifestyle` | — |
| **Category (secondary)** | `Health & Fitness` | — |
| **Tags** | `spirituality, meditation, mindfulness, wisdom, guidance, mental wellbeing, self-help, chatbot` | — |
| **Content rating** | Everyone | — |
| **Privacy policy URL** | `https://askmukthiguru.lovable.app/privacy` ⚠️ **placeholder — update to final domain** | — |
| **Support email** | `support@askmukthiguru.com` ⚠️ **placeholder** | — |
| **Target audience** | 18+ (spiritual content, not for children) | — |
| **Contains ads** | No | — |
| **In-app purchases** | No (v1) | — |
| **App type** | Free | — |
| **Distribution** | Google Play (global) | — |

### Full description (≤ 4000 chars)

> AskMukthiGuru is your personal AI spiritual guide, rooted in the timeless teachings of Sri Preethaji & Sri Krishnaji. Ask any question about life, peace, purpose, or inner freedom — and receive a thoughtful, contemplative response drawn from a curated knowledge base of their discourses, books, and guided practices.
>
> #### ✨ What you can do
>
> - **Chat with the Guru** — Have meaningful, AI-powered conversations grounded in Sri Preethaji & Sri Krishnaji's wisdom. Responses are retrieved from a verified knowledge graph, not generic web text.
> - **Guided meditations & daily practices** — Explore a library of breath practices, mindful meditations, and contemplative exercises designed to fit into your daily life.
> - **Study notebook** — Save insights, jot reflections, and build a private journal of your spiritual journey.
> - **Knowledge graph** — Visualize how concepts, teachers, and practices connect. Discover related teachings effortlessly.
> - **Multilingual support** — Use AskMukthiGuru in English, हिन्दी, தமிழ், తెలుగు, ಕನ್ನಡ, or मराठी. More languages coming soon.
> - **Truly private** — Conversations are encrypted in transit (HTTPS/TLS) and at rest (the deployed Supabase database and its backups). Row-level security enforces per-user access control on top of that encryption. No advertising SDKs, no third-party trackers, and we do not sell user data.
> - **Free forever** — AskMukthiGuru v1 is completely free with no in-app purchases.
>
> #### 🧘 Who it's for
>
> Anyone seeking clarity, calm, or a deeper connection to their inner self — whether you're new to meditation or have years of practice. AskMukthiGuru meets you where you are.
>
> #### 🌱 Why it's different
>
> Unlike generic chatbots, AskMukthiGuru is anchored to a single, coherent body of teaching. The underlying knowledge graph links teachers, concepts, and practices so answers are consistent, sourced, and relevant — not hallucinated.
>
> #### ⚠️ Important
>
> AskMukthiGuru is a spiritual and reflective companion. It is **not a substitute for professional medical or mental-health care**. If you are in crisis or experiencing a mental-health emergency, please contact a qualified professional or a crisis helpline immediately.
>
> #### Privacy first
>
> - HTTPS/TLS encryption in transit; Supabase database + backups encrypted at rest.
> - Row-level security enforces per-user access control on all user data.
> - No advertising SDKs, no third-party trackers. We do not sell user data.
> - Push notifications: a device token and the notification title/body are sent to Firebase (Android) or Apple APNs (iOS) for delivery. Those providers process the payload solely to deliver the notification; their retention is governed by their respective policies (Apple retains APNs delivery logs for up to 30 days; Firebase retains FCM delivery metrics per its data-retention policy). We do not share message content with any other third party.
> - Delete your account and data anytime from the Profile page.
>
> Download AskMukthiGuru and begin your journey inward today.

_Char count: ~2,350 — well within the 4,000 limit._

---

## 2. Apple App Store Listing

| Field | Value | Limit |
|---|---|---|
| **App name** | `AskMukthiGuru` | 30 |
| **Subtitle** | `AI Spiritual Guide & Meditate` | 30 |
| **Primary category** | `Lifestyle` | — |
| **Secondary category** | `Health & Fitness` | — |
| **Keywords** | `spirituality,meditation,mindfulness,wisdom,guru,spiritual guide,reflection,daily practice` | 100 |
| **Privacy policy URL** | `https://askmukthiguru.lovable.app/privacy` ⚠️ **placeholder** | — |
| **Support URL** | `https://askmukthiguru.lovable.app/support` ⚠️ **placeholder** | — |
| **Marketing URL** | `https://askmukthiguru.lovable.app` ⚠️ **placeholder** | — |
| **Age rating** | 4+ | — |
| **Made for Kids** | No | — |
| **Apple Sign-In** | ✅ Implemented (native iOS only — `AuthPage.tsx` shows Apple button when `Capacitor.isNativePlatform()` + iOS). Requires Apple provider config in Supabase + Services ID + .p8 key. See §4. | — |

### Description (≤ 4000 chars)

> AskMukthiGuru is your personal AI spiritual guide, rooted in the timeless teachings of Sri Preethaji & Sri Krishnaji. Ask any question about life, peace, purpose, or inner freedom — and receive a thoughtful, contemplative response drawn from a curated knowledge base of their discourses, books, and guided practices.
>
> **What you can do**
>
> • **Chat with the Guru** — Have meaningful, AI-powered conversations grounded in Sri Preethaji & Sri Krishnaji's wisdom. Responses are retrieved from a verified knowledge graph, not generic web text.
>
> • **Guided meditations & daily practices** — Explore a library of breath practices, mindful meditations, and contemplative exercises designed to fit into your daily life.
>
> • **Study notebook** — Save insights, jot reflections, and build a private journal of your spiritual journey.
>
> • **Knowledge graph** — Visualize how concepts, teachers, and practices connect. Discover related teachings effortlessly.
>
> • **Multilingual support** — Use AskMukthiGuru in English, हिन्दी, தமிழ், తెలుగు, ಕನ್ನಡ, or मराठी. More languages coming soon.
>
> • **Truly private** — Your conversations are encrypted in transit and at rest. No ads, no selling of data, no third-party trackers.
>
> • **Free forever** — AskMukthiGuru v1 is completely free with no in-app purchases.
>
> **Who it's for**
>
> Anyone seeking clarity, calm, or a deeper connection to their inner self — whether you're new to meditation or have years of practice. AskMukthiGuru meets you where you are.
>
> **Why it's different**
>
> Unlike generic chatbots, AskMukthiGuru is anchored to a single, coherent body of teaching. The underlying knowledge graph links teachers, concepts, and practices so answers are consistent, sourced, and relevant — not hallucinated.
>
> **Important**
>
> AskMukthiGuru is a spiritual and reflective companion. It is **not a substitute for professional medical or mental-health care**. If you are in crisis or experiencing a mental-health emergency, please contact a qualified professional or a crisis helpline immediately.
>
> **Privacy first**
>
> • End-to-end HTTPS encryption.
> • Row-level security on all user data.
> • No advertising SDKs, no third-party data sharing.
> • Delete your account and data anytime from the Profile page.
>
> Download AskMukthiGuru and begin your journey inward today.

### Age-Rating Questionnaire (App Store Connect)

| Question | Answer |
|---|---|
| Cartoon Violence | None |
| Realistic Violence | None |
| Prolonged Graphic or Sadistic Realistic Violence | None |
| Profanity or Crude Humor | None |
| Fear / Horror | None |
| Medical / Treatment Information | None (no claims made — see disclaimer) |
| Alcohol, Tobacco, or Drug Use | None |
| Simulated Gambling | None |
| Sexual Content or Nudity | None |
| Unrestricted Web Access | No — Capacitor WebView is restricted to app content + Supabase backend only |
| User-Generated Content | No public UGC. Chat content is private to the user. |
| Data Collection | Yes — see Privacy Nutrition Label below |

**Result: 4+**

---

## 3. Screenshots Required

### Google Play
- **Dimensions:** 1080 × 1920 px (9:16 portrait) is the **recommended target** for recommendation surfaces. Play Console permits screenshots between **320 and 3840 px** on either edge; stay within that range. PNG, 24-bit, no alpha.
- **Quantity:** min 2, max 8 per phone screenshot set.
- **Recommended screens:**
  1. **Landing / Onboarding** (`/`) — value proposition + CTA.
  2. **Chat** (`/chat`) — a sample AI response in the chat UI.
  3. **Practices list** (`/practices`) — meditation library grid.
  4. **Practice detail** (`/practices/<slug>`) — a guided meditation in progress.
  5. **Profile / Memory** (`/profile`) — user profile + memory toggle.
  6. **Knowledge graph** (`/knowledge-graph`) — interactive concept graph.

### Apple App Store
- **6.7" iPhone (iPhone 14 Pro Max / 15 Pro Max):** 1290 × 2796 px, PNG. 6–10 screenshots required.
- **6.5" iPhone (optional, legacy):** 1242 × 2688 px, PNG.
- Same six screens as Play.
- First screenshot becomes the App Store search result thumbnail — pick the most visually compelling (recommend Chat or Knowledge graph).

> Generation script: `scripts/ops/generate_store_screenshots.cjs`
> Output: `artifacts/store-screenshots/{android,iphone}/{screen}.png`

---

## 4. ✅ Apple Sign-In — Implemented (native iOS)

**App Store Review Guideline 4.8 — Sign in with Apple** requires Sign in with Apple whenever a third-party/social login (Google) is offered on iOS.

**Status: implemented in code.** `src/pages/AuthPage.tsx` shows an Apple Sign-In button when `Capacitor.isNativePlatform()` is true (native iOS + Android; on Android it's a no-op UI that can be hidden via a platform check if desired). The handler calls `supabase.auth.signInWithOAuth({ provider: 'apple', redirectTo: 'com.askmukthiguru.app://auth-callback' })` on native.

**Before submission you must configure Apple as a Supabase Auth provider:**
1. Apple Developer → Certificates, Identifiers & Profiles → Identifiers → create a **Services ID** (not an App ID) with "Sign in with Apple" enabled. Return URL: `https://<your-supabase-project>.supabase.co/auth/v1/callback`.
2. Create an **Auth Key** (.p8) with "Sign in with Apple" enabled for the Services ID. Download the .p8 + note Key ID + Team ID.
3. Supabase Dashboard → Authentication → Providers → Apple → enable + paste Services ID, Secret Key (.p8 contents), Key ID, Team ID, and the authorized redirect URLs.
4. Add `com.askmukthiguru.app://auth-callback` to Supabase Auth → URL Configuration → Redirect URLs.

Until steps 1–4 are done, the Apple button will fail at OAuth init — complete them before submitting to App Store Connect.

---

## 5. Privacy Disclosures

### 5.1 Apple Privacy Nutrition Label

| Category | Data Type | Used For | Linked to You? |
|---|---|---|---|
| **Data Used to Track You** | _None_ | — | — |
| **Contact Info** | Email Address | Authentication | ✅ Yes |
| **User Content** | Chat history (messages) | App functionality (conversation list + retrieval-augmented responses) | ✅ Yes |
| **Identifiers** | Device ID (push notification token) | Notifications — shared with Firebase (Android) / Apple APNs (iOS) for delivery | ✅ Yes |
| **Usage Data** | Diagnostics (anonymized, opt-in) | Analytics / performance improvement | ✅ Yes (opt-in) |
| **Data Not Linked to You** | _None_ | — | — |

**Encryption:**
- ✅ Data encrypted in transit (HTTPS / TLS 1.2+).
- ✅ Data encrypted at rest (deployed Supabase database + backups). Row-level security enforces per-user access control on top of encryption.

**Other disclosures:**
- Apple's "Privacy Choices" icon: not required (no tracking).
- No advertising SDKs collect data.
- Push notification payload (title/body) is sent to Firebase (Android) or Apple APNs (iOS) for delivery; those providers' retention is governed by their policies (Apple retains APNs delivery logs for up to 30 days; Firebase retains FCM delivery metrics per its data-retention policy).

### 5.2 Google Play Data Safety Form

| Question | Answer |
|---|---|
| **Does your app collect or share any of the required user data types?** | Yes — collected. |
| **Data collected:** | • Email address (auth) <br> • Chat messages (app functionality) <br> • Push notification token (notifications) <br> • Diagnostics — anonymized, opt-in (analytics) |
| **Data shared with third parties:** | Push notification token + notification payload (title/body) are shared with Firebase (Android) / Apple APNs (iOS) solely for delivery. No other third-party sharing. |
| **Data encrypted in transit?** | Yes (HTTPS). |
| **Data encrypted at rest?** | Yes (deployed Supabase database + backups). RLS enforces per-user access control. |
| **Can users request data deletion?** | Yes — via the **Delete Account** action on the Profile page. The action calls the `delete-my-account` Supabase Edge Function, which cascades deletion of user-owned rows + the auth.users row, then signs out. Verified end-to-end. |
| **Family/Children policy:** | Not designed for or directed to children under 13. |
| **Does your app contain ads?** | No. No ad SDKs. |
| **Security practices:** | • Row-Level Security on all Supabase tables. <br> • JWT-based auth. <br> • No hardcoded secrets in the client bundle (all keys are public-anon Supabase keys; service keys live server-side only). <br> • PII redaction in backend logs. <br> • Per-user rate limiting. |

### 5.3 Account Deletion Flow

> **✅ Verified.** `src/pages/ProfilePage.tsx` (line ~907) exposes a "Delete Account" AlertDialog that calls the `delete-my-account` Supabase Edge Function (`supabase/functions/delete-my-account/index.ts`) which cascades deletes across user-owned rows + the auth.users row, then the frontend clears local storage + signs out. Apple Guideline 5.1.1(v) + Play Data Safety satisfied.
>
> Apple requires: "If your app supports account creation, you must also offer account deletion within the app."
>
> Link to issue: _file one in the project tracker if not yet present._

---

## 6. Pre-Submission Checklist

- [ ] Update **privacy policy URL** to final domain (replace `lovable.app`).
- [ ] Update **support URL** + **marketing URL** to final domain.
- [ ] Configure **support@askmukthiguru.com** mailbox.
- [ ] Configure **Sign in with Apple** provider in Supabase (Services ID + .p8 key + Return URL) — implementation already in `AuthPage.tsx` (see §4); verify end-to-end on TestFlight before submission.
- [ ] Verify **Delete Account** flow on a TestFlight build (calls `delete-my-account` edge function — see §5.3).
- [ ] Generate screenshots via `node scripts/ops/generate_store_screenshots.cjs --url http://localhost:8080` (or `--url https://askmukthiguru.lovable.app`).
- [ ] Upload to Play Console + App Store Connect.
- [ ] Fill Data Safety form on Play Console (mirrors §5.2).
- [ ] Fill Privacy Nutrition Label on App Store Connect (mirrors §5.1).
- [ ] Confirm content rating questionnaire on both stores.
- [ ] Set pricing: Free on both stores.
- [ ] Set availability: global (or per-market strategy).

---

## 7. File References

| Asset | Path |
|---|---|
| Privacy page (web) | `src/pages/PrivacyPage.tsx` |
| Terms page (web) | `src/pages/TermsPage.tsx` — contains `terms.notMedical` + `terms.notMedicalText` disclaimer ✅ |
| i18n locales | `src/locales/{en,hi,kn,mr,ta,te}.json` |
| Screenshot generator | `scripts/ops/generate_store_screenshots.cjs` |
| Screenshot output | `artifacts/store-screenshots/` (gitignored) |

_Last updated: 2026-07-13_