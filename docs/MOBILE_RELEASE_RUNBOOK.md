# Mobile App Release Runbook — AskMukthiGuru (Android + iOS)

Step-by-step submission guide for shipping the Capacitor-wrapped app to Google Play and the Apple App Store.

**Package id:** `com.askmukthiguru.app`
**Display name:** `AskMukthiGuru`
**Wrapper:** Capacitor 8 around the Vite/React frontend build.

---

## 1. Prerequisites

| Requirement | Cost | Notes |
| --- | --- | --- |
| Google Play Console account | $25 one-time | Required for Android distribution. |
| Apple Developer Program | $99/year | Required for iOS distribution. |
| D-U-N-S number | Free | Required only for Apple **organization** accounts (not individual). Lookup at https://developer.apple.com/programs/enroll/ . |
| Verified accounts | — | Both Google and Apple require identity verification before publishing. Apple org accounts require D-U-N-S + legal entity verification (can take several days). |
| Apple Developer Team ID | — | Found in Apple Developer → Membership. Needed for APNs (set `APNS_TEAM_ID`). |
| Firebase project | Free | For Android FCM push. See §7. |

> Plan ahead: Apple org account verification typically takes 1–2 weeks. Start it first.

---

## 2. Build the App

```bash
# From repo root
npm run cap:sync
```

`cap:sync` runs `vite build` then `npx cap sync` — copies the production web bundle (`dist/`) into the native projects and updates native plugin dependencies.

```bash
npm run cap:open:android   # opens android/ in Android Studio
npm run cap:open:ios       # opens ios/App in Xcode
```

- `cap:open:android` — launches Android Studio so you can build/run/sign/submit the AAB.
- `cap:open:ios` — launches Xcode so you can archive/sign/submit the IPA.

> If you change the package id or add/remove Capacitor plugins, re-create the native projects:
> ```bash
> rm -rf android ios && npx cap add android && npx cap add ios
> ```
> Only do this when necessary — it discards native-side customizations.

Icons/splash regeneration (from `public/icon-512.png`):
```bash
python3 scripts/ops/generate_mobile_assets.py
```

---

## 3. Android Signing

### 3.1 Generate the keystore
```bash
keytool -genkey -v -keystore android/askmukthiguru.keystore \
  -alias askmukthiguru -keyalg RSA -keysize 2048 -validity 10000
```
> Keep this keystore **forever**. Lose it → you can never update the app on Play Store. Back up to a secure password manager / hardware key.

### 3.2 Create `android/key.properties` (gitignored)
```properties
storeFile=../askmukthiguru.keystore
storePassword=***
keyAlias=askmukthiguru
keyPassword=***
```

### 3.3 Wire up the signing config in `android/app/build.gradle`
Task 8 left a comment block at the top of the `android { ... }` block. Uncomment and replace with:

```gradle
def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('key.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    // ... existing namespace / defaultConfig ...

    signingConfigs {
        release {
            storeFile file(keystoreProperties['storeFile'])
            storePassword keystoreProperties['storePassword']
            keyAlias keystoreProperties['keyAlias']
            keyPassword keystoreProperties['keyPassword']
        }
    }

    buildTypes {
        release {
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
            signingConfig signingConfigs.release
        }
    }
}
```

### 3.4 Build the AAB
In Android Studio: **Build → Generate Signed Bundle / APK → Android App Bundle → release**. Output: `android/app/build/outputs/bundle/release/app-release.aab`.

---

## 4. iOS Signing

1. Open `ios/App` in Xcode (`npm run cap:open:ios`).
2. Select the **App** target → **Signing & Capabilities** tab.
3. Tick **Automatically manage signing**, select your **Team**, and ensure the **Bundle Identifier** is `com.askmukthiguru.app`.
4. Xcode will auto-create the provisioning profile + signing certificate for development.
5. For App Store distribution: **Product → Archive**. In the Organizer window choose **Distribute App → App Store Connect → Upload** (or `Export` to produce an `.ipa` for manual upload).

> If automatic signing fails, create the provisioning profile manually in https://developer.apple.com/account/resources/profiles and import it.

---

## 5. Google Play Submission

### 5.1 Generate store screenshots first
```bash
node scripts/ops/generate_store_screenshots.cjs
```
Output goes to `docs/store_screenshots/` (or the path the script prints). Play Console requires 2–8 screenshots per device form factor (phone, 7-inch tablet, 10-inch tablet).

### 5.2 Create the app in Play Console
1. Go to https://play.google.com/console → **Create app**.
2. App details, store listing copy, screenshots, feature graphic, privacy policy URL — fill from `docs/STORE_LISTING.md`.
3. Set content rating via the IARC questionnaire.
4. Set target audience + data safety form (declare: emails, names, app activity, device IDs — match what your app actually collects).

### 5.3 Upload the AAB and progress through testing tracks
1. **Internal testing** — upload AAB, add your own tester email, install on a real device via the opt-in link. Smoke test OAuth + push + chat.
2. **Closed testing** — for personal accounts created after Nov 13 2023, Google requires **20 testers opted-in for 14 consecutive days** before production release. Add testers via email list or Google Group.
3. **Open testing** — public beta via Play Store listing (optional but recommended for soak testing at scale).
4. **Production** — submit for review. Review typically 1–3 days for first submission; longer for new accounts.

### 5.4 Update versioning
Bump `versionCode` (integer, must increase each upload) and `versionName` (human-readable) in `android/app/build.gradle` for every release.

---

## 6. App Store Submission

### 6.1 Archive and upload
1. Xcode → **Product → Archive**.
2. Organizer → **Distribute App → App Store Connect → Upload**.
3. Wait for Apple to process the build (visible in App Store Connect → TestFlight within ~15 min).

### 6.2 Fill the App Store listing
In App Store Connect → **My Apps → AskMukthiGuru → App Store** tab:
- Name, Subtitle, Privacy Policy URL, Category (Lifestyle / Health & Fitness) — copy from `docs/STORE_LISTING.md`.
- App screenshots (generated by `generate_store_screenshots.cjs`) — required for 6.7" + 6.5" + 5.5" phone sizes at minimum.
- App Preview video (optional but recommended).
- App Review contact info + demo account credentials (if any).

### 6.3 TestFlight
1. **Internal testing** — add App Store Connect users as internal testers. Build available immediately.
2. **External testing** — invite external email testers; requires a brief beta app review (usually <24h).
3. Collect crash + feedback reports via TestFlight for at least a day before production submit.

### 6.4 Submit for review
From the App Store tab → **Add for Review**. First review typically 24–48h. Approve the phased rollout:
- Day 1: 1% → Day 2: 2% → Day 3: 5% → Day 4: 10% → Day 5: 20% → Day 6: 50% → Day 7: 100%.
- You can pause the rollout at any phase if crash spikes appear.

### 6.5 Update versioning
Bump `CFBundleShortVersionString` (e.g. `1.0.0`) and `CFBundleVersion` (build number, must increase each upload) in `ios/App/App/Info.plist` for every release.

---

## 7. Push Notification Credentials

### 7.1 Android — Firebase Cloud Messaging (FCM)
1. Go to https://console.firebase.google.com → **Add project** (name: `askmukthiguru`).
2. **Project Settings → Add app → Android** → package name `com.askmukthiguru.app` → register.
3. Download `google-services.json` → place at `android/app/google-services.json` (**gitignored**). The `build.gradle` block at the bottom of `android/app/build.gradle` auto-applies the `com.google.gms.google-services` plugin when this file is present.
4. **Project Settings → Cloud Messaging → (legacy) Server key** — not needed; we use service-account auth instead.
5. **Project Settings → Service Accounts → Generate new private key** → downloads a JSON. Set on the backend:
   ```bash
   FIREBASE_CREDENTIALS_JSON=<paste the entire JSON contents, OR a path to the JSON file>
   ```
   The backend `push_service.py` reads this env var, authenticates with `firebase-admin`, and sends FCM messages.

### 7.2 iOS — APNs
1. Apple Developer → **Certificates, Identifiers & Profiles → Keys → +**.
2. Name: `AskMukthiGuru APNs`, enable **Apple Push Notifications service (APNs)**.
3. Download the `.p8` file (**gitignored**) — only downloadable once. Save as e.g. `ios/AuthKey_APNs.p8`.
4. Note the **Key ID** (shown on the key page) and your **Team ID** (Membership page).
5. Set on the backend:
   ```bash
   APNS_KEY_ID=<10-char key id>
   APNS_TEAM_ID=<10-char team id>
   APNS_KEY_PATH=/path/to/AuthKey_APNs.p8     # OR paste the PEM-formatted key as APNS_KEY_PEM
   APNS_KEY_PEM=                              # optional: inline PEM (-----BEGIN PRIVATE KEY-----...)
   APNS_BUNDLE_ID=com.askmukthiguru.app
   ```
   Provide either `APNS_KEY_PATH` (preferred) or `APNS_KEY_PEM` (for serverless / no-filesystem deployments).
6. **Optional — also upload the same `.p8` to Firebase** (Console → Project Settings → Cloud Messaging → APNs Authentication Key). This lets FCM fan out to iOS devices via APNs as a *secondary* path. The authoritative path for AskMukthiGuru is **direct backend dispatch** in `backend/services/push_service.py:_send_apns`, which signs its own APNs JWT using `APNS_KEY_ID`, `APNS_TEAM_ID`, and `APNS_KEY_PATH`/`APNS_KEY_PEM`. Uploading the key to Firebase does **not** replace those backend env vars — they are still required for iOS push. Configure both only if you want FCM as a redundant fan-out channel; otherwise the backend-only path is sufficient.

### 7.3 Apply the push devices migration
The backend stores device tokens in `push_devices` (per-user, per-platform).

```bash
npx supabase db push
```

Or apply directly against prod Supabase SQL Editor:
```sql
-- file: supabase/migrations/20260713000000_create_push_devices.sql
-- (apply the full file contents)
```

> Note: this migration uses a distinct trigger function name `push_devices_touch_updated_at()` to avoid clobbering the shared `touch_updated_at()` used by other tables.

---

## 8. Supabase OAuth Redirect URLs

In Supabase Dashboard → **Authentication → URL Configuration → Redirect URLs**, add:

```
com.askmukthiguru.app://auth-callback
https://askmukthiguru.lovable.app/auth
```

- `com.askmukthiguru.app://auth-callback` — native deep link captured by `App.addListener('appUrlOpen')` (registered in `src/App.tsx`) on both Android (intent-filter) and iOS (CFBundleURLTypes). Supabase OAuth completes in the system browser then hands control back to the app.
- The production web URL — for browser-based auth fallback.

Also set the **Site URL** to the production web URL (`https://askmukthiguru.lovable.app`).

> Do NOT use `window.location.origin` on native — it is `https://localhost` inside the Capacitor WebView and Supabase will reject the redirect.

---

## 9. Pre-Submission Checklist

- [ ] **Apple Sign-In** (Apple Guideline 4.8) — implemented in `src/pages/AuthPage.tsx` (Apple button shown on native). Before submission: configure Apple as a Supabase Auth provider (Services ID + .p8 key + Return URL `https://<project>.supabase.co/auth/v1/callback`), then verify end-to-end on a TestFlight build that the Apple button completes OAuth and lands the user on `/chat`.
- [ ] **Delete-account flow** (Apple Guideline 5.1.1) — implemented in `src/pages/ProfilePage.tsx` (calls the `delete-my-account` Supabase Edge Function, which cascades user-owned row deletes + the auth.users row, then signs out + clears local storage). Before submission: verify on a TestFlight build that tapping **Delete Account** removes the auth user and signs the session out.
- [ ] Screenshots generated via `node scripts/ops/generate_store_screenshots.cjs`.
- [ ] Privacy policy live at a public HTTPS URL (listed in `docs/STORE_LISTING.md`).
- [ ] Support email reachable and monitored.
- [ ] `versionCode` (Android) and `CFBundleVersion` (iOS) bumped.
- [ ] Store listing copy reviewed against `docs/STORE_LISTING.md`.
- [ ] Push notifications tested end-to-end on a real device (Android FCM + iOS APNs).
- [ ] OAuth deep-link tested on a real device (Google Sign-In → returns to app).
- [ ] Splash + status bar styling verified in both light + dark mode on iOS.
- [ ] App does not crash on cold launch with no network.

---

## 10. Post-Launch

- **Crash monitoring**
  - Firebase Crashlytics (optional, free) — add `@capacitor-community/crashlytics` or native SDK.
  - Google Play Console → **Android vitals → Crashes & ANRs** — review daily for the first week.
  - App Store Connect → **Metrics** (crashes are visible after enough volume).
- **TestFlight feedback** — read tester comments in App Store Connect → TestFlight → Feedback. Address before widening rollout.
- **Phased rollout** — pause if crash-free usersessons drops below 99.5% or ANR rate spikes.
- **Version bumps** — for every update, bump `versionCode` + `CFBundleVersion`. Never reuse a version code.
- **Store reviews** — respond to user reviews in both consoles within 24h where possible.
- **Privacy policy** — keep in sync with any new data collection. Apple/Google will reject updates that mismatch the published policy.