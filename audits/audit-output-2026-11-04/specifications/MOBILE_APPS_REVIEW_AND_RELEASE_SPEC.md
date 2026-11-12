# Mobile apps (Android and iOS): review and release specification

## 0. Header

| Field | Value |
|---|---|
| Purpose | Review the Capacitor 8 mobile apps, which the 2026-11-04 audit package did not review. Give an implementation agent a finding register, a store-readiness checklist and an ordered task list. |
| Status | **Review complete from static reading. Mobile is NOT submission-ready.** No native app was built. No device, emulator, store console or live backend was used. Every finding is from reading files. |
| Date | 2026-11-06 |
| Code head | `fb5cab0f` on `feature/audit-strengthen-rag-qdrant` |
| Depends on decisions | Existing: D-21 (proactive features opt-in), D-22 (native review scope), N-03 (second mobile codebase, `19-build-redesign-consolidate-remove-avoid.md:84`). Proposed here: D-PMOB1 to D-PMOB8 (section 8). |
| Owner of finding IDs | Not assigned in `CONVENTIONS.md` section 5. The IDs `MOB-01` to `MOB-15` are **proposals**. The lead confirms them in `findings-index.md`. |
| Evidence labels | As in `CONVENTIONS.md` section 3. `[V-STATIC]` means: read at `fb5cab0f` in this session. `[INF]` means: inferred, with the basis stated. External store rules were **not** fetched in this session. Rules stated from memory carry `[INF]`. Confirm them against the live store pages before you act. |
| Severity | Scale in `CONVENTIONS.md` section 4. No finding is P0: none is a data-integrity or security fault proven by reading. Five are P1 (store or user-experience blockers). |
| Reading order | Section 2 is context. Section 3 holds the findings. Section 4 is the owner checklist. Section 7 holds the work order. |

Rules that bind this review (from root `CLAUDE.md`):

1. `android/` and `ios/` are Capacitor 8 projects. Read `docs/MOBILE_RELEASE_RUNBOOK.md` before any store work.
2. Mobile is not submission-ready.
3. Secrets stay in environment variables. This document names signing-related files and line numbers only. It quotes no secret value.
4. The assistant never speaks in a teacher's first person. Teacher words are verbatim spans only. Mobile must not change this.
5. Railway is stopped until the owner says otherwise (`CLAUDE.md`, Gotchas). A native build that points at Railway cannot work until then.

---

## 1. Existing coverage and what it lacks

| Source | What it covers | What it lacks |
|---|---|---|
| `docs/MOBILE_RELEASE_RUNBOOK.md` (265 lines) | Accounts, build commands (`:26-52`), Android signing (`:56-106`), iOS signing (`:110-118`), Play and App Store steps (`:122-172`), push credentials (`:176-218`), OAuth redirect URLs (`:222-236`), pre-submission checklist (`:240-252`), post-launch (`:256-266`). | No code review. Three claims are stale or wrong against the code (MOB-01, MOB-08, MOB-10). It asks the reader to edit `build.gradle` by hand (`:73-103`), but the file is already wired (`android/app/build.gradle:3-49,68-87`). It has no privacy-manifest step, no permission review and no native test plan. The checklist boxes (`:242-251`) are all unchecked. |
| `mobile/MOBILE_DEPLOY_CONFIDENCE.md` | Fastlane quickstart, store copy, a privacy data map. | It says `android/` and `ios/` are gitignored (`:12`). They are tracked (74 files by `git ls-files android ios`). It says the inference path uses local Ollama only and calls no external LLM API (`:113-116`). Root `CLAUDE.md` says `LLM_PROVIDER=openrouter` is live. It marks Apple labels "pending audit" (`:118-120`). |
| `docs/STORE_LISTING.md` | Listing copy, privacy label tables (`:184-216`), deletion note (`:218-228`). | The privacy URL and support email are placeholders (`:18`, `:19`). It does not list Sentry (MOB-04). Its deletion note says the backend purge is skipped with a warning if `BACKEND_URL` is unset (`:224`). The function now refuses to delete instead (`supabase/functions/delete-my-account/index.ts:46-51`). |
| `mobile/fastlane-android-Fastfile`, `mobile/fastlane-ios-Fastfile` | Draft lanes. | They sit in `mobile/`, not in `android/fastlane/` or `ios/fastlane/`. No `Appfile` or `Matchfile` is tracked. The Android lane does not match the Gradle signing code (MOB-08). |
| `mobile/expo/` | A separate Expo SDK 54 companion client. | Its README lists credentials, session handling, native permissions and EAS signing as release-gated work (`mobile/expo/README.md:3`). |
| Audit package `audits/audit-output-2026-11-04/` | Mentions mobile only as a viewport in tests and as N-03 (`19-...md:84`). The Mobile Safari job failure is recorded (`01-...md:343`). | No review of `android/`, `ios/`, `capacitor.config.ts` or native-branch code. This document fills that gap. |

---

## 2. Current state (verified)

### 2.1 Project shape

| Item | Value | Evidence |
|---|---|---|
| Wrapper | Capacitor. `@capacitor/core ^8.5.3`, `/cli ~8.4.3`, `/android ^8.5.3`, `/ios ^8.5.3`. | `package.json:32-37,111-112` [V-STATIC] |
| Plugins | `app`, `device`, `preferences`, `push-notifications`. No `browser`, `haptics`, `share`, `local-notifications`, `filesystem`. | `package.json:32-37`; `ios/App/CapApp-SPM/Package.swift:15-18` [V-STATIC] |
| App id and name | `com.askmukthiguru.app`, `AskMukthiGuru`. | `capacitor.config.ts:4-5` [V-STATIC] |
| Web dir and schemes | `dist`. `androidScheme: https`, `iosScheme: capacitor`. | `capacitor.config.ts:6-9` [V-STATIC] |
| Server URL | None. The app loads the bundled `dist/` (no `server.url`). | `capacitor.config.ts:7-10` [V-STATIC] |
| Mobile build | `vite build --mode mobile`; `cap:sync` runs it, then `cap sync`. | `package.json:19-24` [V-STATIC] |
| Routing on native | `HashRouter`. | `src/App.tsx:189-194` [V-STATIC] |
| Tracked native files | 74 under `android/` and `ios/`. | `git ls-files android ios` [V-STATIC] |
| Generated, ignored | `ios/App/App/capacitor.config.json`, `config.xml`, `App/App/public`. | `ios/.gitignore:4,12-13` [V-STATIC] |

### 2.2 Android

| Item | Value | Evidence |
|---|---|---|
| `minSdk` / `compileSdk` / `targetSdk` | 24 / 36 / 36 | `android/variables.gradle:2-4` [V-STATIC] |
| `versionCode` / `versionName` | 1 / "1.0.0", hard-coded | `android/app/build.gradle:58-59` [V-STATIC] |
| Release build | `minifyEnabled true` with the default ProGuard file. | `android/app/build.gradle:81-82` [V-STATIC] |
| Release signing | Reads `ANDROID_KEYSTORE_*` / `ANDROID_KEY_*` env vars, then `key.properties`. Throws on any `assemble/bundle/package/publish/upload ... Release` task if no key. | `build.gradle:3-49,119-138` [V-STATIC] |
| Committed secrets | None found by file name. Tracked: `android/key.properties.example` (placeholders only, `:38,:44`). Ignored: `*.jks`, `*.keystore`, `key.properties`, `google-services.json`, `*.p8`. | `.gitignore:29-33,40`; `android/.gitignore:56-58`; `git ls-files` shows no `.jks`, `.keystore`, `key.properties`, `google-services.json`, `.p8` [V-STATIC] |
| Permissions | `INTERNET`, `POST_NOTIFICATIONS`. Nothing else. | `AndroidManifest.xml:54-55` [V-STATIC] |
| Backup | `android:allowBackup="true"`. No backup rules file. | `AndroidManifest.xml:5` [V-STATIC] |
| Network security config | None tracked. No `networkSecurityConfig` attribute, no `usesCleartextTraffic`. | `AndroidManifest.xml:4-10`; `git ls-files` finds no `network_security*` [V-STATIC] |
| Deep link | Custom scheme `com.askmukthiguru.app://auth-callback`, `autoVerify="false"`. No `https` App Link. | `AndroidManifest.xml:25-30` [V-STATIC] |
| Activity | `singleTask`, `exported="true"` (needed for the launcher). | `AndroidManifest.xml:12-18` [V-STATIC] |
| FileProvider | `exported="false"`; `file_paths.xml` exposes `external-path` and `cache-path` at `.`. | `AndroidManifest.xml:34-42`; `res/xml/file_paths.xml:3-4` [V-STATIC] |
| Firebase | Gradle applies the Google services plugin only if `google-services.json` exists. It is ignored, so push is inert until supplied. | `build.gradle:110-117` [V-STATIC] |
| Native tests | `ExampleUnitTest.java`, `ExampleInstrumentedTest.java` (template files). | `git ls-files android` [V-STATIC] |

### 2.3 iOS

| Item | Value | Evidence |
|---|---|---|
| Deployment target | 15.0 (Xcode project and Swift package `.iOS(.v15)`). | `project.pbxproj:235,286,304,327`; `Package.swift:8` [V-STATIC] |
| Bundle id | `com.askmukthiguru.app`. | `project.pbxproj:311,333` [V-STATIC] |
| Version / build | `MARKETING_VERSION = 1.0`, `CURRENT_PROJECT_VERSION = 1`. | `project.pbxproj:302,309,325,332` [V-STATIC] |
| Signing | `CODE_SIGN_STYLE = Automatic`. No `DEVELOPMENT_TEAM` entry. | `project.pbxproj:301,324`; grep finds no `DEVELOPMENT_TEAM` [V-STATIC] |
| Privacy manifest | **No `PrivacyInfo.xcprivacy` is tracked.** | `git ls-files ios` (full list in section 1 evidence) [V-STATIC] |
| Usage strings | **None.** Info.plist has no `NS*UsageDescription` key. | `ios/App/App/Info.plist:1-68` [V-STATIC] |
| ATS | No `NSAppTransportSecurity` key, so the default (HTTPS only) applies. | `Info.plist:1-68` [V-STATIC] |
| Background modes | `remote-notification` only. No `audio`. | `Info.plist:38-41` [V-STATIC] |
| Encryption export | `ITSAppUsesNonExemptEncryption = false`. | `Info.plist:36-37` [V-STATIC] |
| URL scheme | `com.askmukthiguru.app`. No associated domains entitlement. | `Info.plist:25-35`; `App.entitlements:1-8` [V-STATIC] |
| Push entitlement | `aps-environment = development`. | `ios/App/App/App.entitlements:5` [V-STATIC] |
| Device capability | `UIRequiredDeviceCapabilities = armv7`. | `Info.plist:50-53` [V-STATIC] |
| Orientation | Portrait on iPhone; all four on iPad. | `Info.plist:54-64` [V-STATIC] |
| Link handlers | `AppDelegate` forwards `open url` and `continue userActivity` to Capacitor. | `AppDelegate.swift:36,42` [V-STATIC] |

### 2.4 Web code that branches on the native platform

| Behaviour | Evidence |
|---|---|
| Native detection: `Capacitor.isNativePlatform()` in 10 files (`App.tsx`, `AuthPage.tsx`, `Index.tsx`, `backendUrl.ts`, `chatStorage.ts`, `memoryApi.ts`, `sentry.ts` (comment), `CookieConsentBanner.tsx`, `PushNotificationsManager.tsx`, `PushPermissionPrompt.tsx`). | `grep -rn Capacitor src` [V-STATIC] |
| Backend URL: `VITE_BACKEND_URL` first. Then prod Railway URL if `VITE_NATIVE_BACKEND=prod` or the host is a prod host. Else empty (calls fail closed). | `src/lib/backendUrl.ts:31-57` [V-STATIC] |
| Mobile env file sets `VITE_BACKEND_URL` to the prod Railway URL. The file is tracked. | `.env.mobile:3` [V-STATIC] |
| OAuth: `signInWithOAuth` for Google and Apple with `redirectTo = com.askmukthiguru.app://auth-callback` on native. No `skipBrowserRedirect`, no `@capacitor/browser`. | `AuthPage.tsx:566,614,754`; `src/lib/authConstants.ts:7`; grep finds no `skipBrowserRedirect` or `Browser.open` in `src/` [V-STATIC] |
| Deep-link handler: `appUrlOpen` listener, mounted only while `AuthPage` is mounted. Handles PKCE `code` and implicit tokens. | `AuthPage.tsx:160-197` [V-STATIC] |
| Apple button shown on native only; Google One Tap and cookie banner are off on native. | `AuthPage.tsx:1031,776`; `Index.tsx:80`; `CookieConsentBanner.tsx:80` [V-STATIC] |
| Push: permission is requested on mount if status is `prompt`; token is posted once to `/api/push/register`; deep links are allow-listed. | `PushNotificationsManager.tsx:18-20,68-103`; mounted at `App.tsx:384` [V-STATIC] |
| Local chat history uses Capacitor `Preferences` on native. | `src/lib/chatStorage.ts:9-16` [V-STATIC] |
| Sentry runs in native builds if a DSN exists; error replay is on at 0.5 with masking. | `src/lib/sentry.ts:6-9,19-30` [V-STATIC] |
| Cited clips play in a YouTube iframe with `origin=window.location.origin`, or in a `<video autoPlay playsInline>` for direct streams. | `CitationCard.tsx:245-251,274-281`; `DiscourseAudioStrip.tsx:306-313` [V-STATIC] |
| Voice input: `getUserMedia({ audio: true })` and `MediaRecorder`. | `src/hooks/useSpeechRecognition.ts:127,240,256` [V-STATIC] |
| Helplines: `tel:` links from a bundled list (Tele-MANAS 14416, 112, Vandrevala, 988). | `src/lib/crisisHelplines.ts:26-60`; `CrisisLines.tsx:16`; `ChatMessage.tsx:1306` [V-STATIC] |
| Account deletion: Profile > `AccountDataCard` > "Delete Account" > `CancelFlow`. "Delete immediately" calls the `delete-my-account` edge function, then clears local data and signs out. The other retention options sign out and show "Deletion scheduled". | `AccountDataCard.tsx:140-190`; `CancelFlow.tsx:37,81` [V-STATIC] |

### 2.5 CI

| Item | Evidence |
|---|---|
| Two workflows build the web bundle in mobile mode. | `.github/workflows/lint-test.yml:82-83`; `production-readiness.yml:46-47` [V-STATIC] |
| No workflow runs `cap sync`, `gradlew`, `xcodebuild`, Fastlane or a native test. | `grep -n -i 'gradle\|xcodebuild\|fastlane\|cap sync' .github/workflows/*.yml` returns no match [V-STATIC] |

---

## 3. Findings register

Format follows `CONVENTIONS.md` section 4, shortened. Confidence is stated in the Type column. No finding was reproduced on a device.

### MOB-01 — OAuth runs inside the WebView; Google sign-in is likely blocked

| Field | Value |
|---|---|
| Severity | **P1** |
| Type | Probable defect |
| Evidence | `signInWithOAuth({ provider: 'google' ... })` with no `skipBrowserRedirect`: `AuthPage.tsx:563-570`, `:611-618`, `:751-758`. No `@capacitor/browser` in `package.json:32-37`. Runbook `:231` says OAuth "completes in the system browser". No code opens the system browser. [V-STATIC] |
| Impact | `supabase-js` by default sets `window.location` to the provider URL. In a Capacitor WebView this loads Google's page inside the app WebView. Google rejects OAuth from embedded WebViews (`disallowed_useragent`). [INF: Google secure-browser policy, not re-fetched.] Google sign-in then fails on Android and iOS. Apple sign-in (a web flow) may work but is also unproven. Email sign-in is not affected by this finding. |
| Fix | Add `@capacitor/browser`. Call `signInWithOAuth` with `skipBrowserRedirect: true`. Open the returned URL with `Browser.open`. Close the browser on `appUrlOpen`. For Apple, prefer native Sign in with Apple (D-PMOB2). |
| Verification | `[HUMAN]` device test (AC-MOB-01). |

### MOB-02 — No iOS privacy manifest

| Field | Value |
|---|---|
| Severity | **P1** |
| Type | Confirmed defect (file absent). The store consequence is `[INF]`. |
| Evidence | No `PrivacyInfo.xcprivacy` in `git ls-files ios`. The app uses `@capacitor/preferences` (`chatStorage.ts:5`, `AuthPage.tsx:18`), which stores values in `UserDefaults` on iOS [INF: plugin behaviour, source not read]. `UserDefaults` is a "required reason" API in Apple's privacy rules [INF]. |
| Impact | Apple has required a privacy manifest with declared API reasons for app uploads since 2024 [INF; confirm at upload]. A missing manifest can fail upload validation or trigger a review rejection. |
| Fix | Add `ios/App/App/PrivacyInfo.xcprivacy` to the App target. Declare `NSPrivacyTracking = false`, no tracking domains, the collected data types that match the final privacy label (MOB-04), and the required-reason API codes the app and plugins use. Check each plugin's own manifest in `node_modules` after `cap sync`. |
| Verification | `xcodebuild archive`, then "Generate Privacy Report" in Xcode (`[HUMAN]`, macOS). |

### MOB-03 — Microphone is used with no permission or usage string

| Field | Value |
|---|---|
| Severity | **P1** |
| Type | Probable defect |
| Evidence | `useSpeechRecognition.ts:240` calls `getUserMedia({ audio: true })`. The Android manifest lists only `INTERNET` and `POST_NOTIFICATIONS` (`AndroidManifest.xml:54-55`). `Info.plist` has no `NSMicrophoneUsageDescription` (`:1-68`). `ChatInterface.tsx:730` mounts the hook. [V-STATIC] |
| Impact | iOS: an app that reaches the microphone without a usage string can be terminated by the OS, and Apple rejects it on review [INF]. Android: the WebView cannot get the microphone without `RECORD_AUDIO`, so voice input fails. Whether the mic button shows on native was not checked. |
| Fix | Decide whether voice input ships in v1 (D-PMOB3). If yes: add `RECORD_AUDIO` and `MODIFY_AUDIO_SETTINGS`, add `NSMicrophoneUsageDescription` with a plain reason, and request permission at the first tap, not at launch. If no: hide the mic control when `isNativePlatform()` and add a test. |
| Related | `useVoiceInput.ts:15-16,113` reads `VITE_API_BASE_URL`, not `BACKEND_URL`. `.env.mobile` sets only `VITE_BACKEND_URL`. That hook then reports "Voice endpoint not configured" on native. Its caller is `MoodCheckIn.tsx` [V-STATIC]. |

### MOB-04 — Privacy disclosures do not match the code or each other

| Field | Value |
|---|---|
| Severity | **P1** |
| Type | Confirmed defect in documents; store consequence `[INF]` |
| Evidence | (a) `STORE_LISTING.md:207-216` and `:50-58` list no crash or error reporting. Sentry with error replay is enabled in native builds (`sentry.ts:6-9,19-20`). (b) `MOBILE_DEPLOY_CONFIDENCE.md:113-116` says no external LLM API is called. Root `CLAUDE.md` says `LLM_PROVIDER=openrouter` is the live default. The first-person route calls no LLM for answer text, but its gate and relevance steps do (`CLAUDE.md` invariants 19, 22, 24) [DOC-CLAIM]. (c) `STORE_LISTING.md:202,216` say "No other third-party sharing" and "no third-party trackers". (d) Store privacy URL and support email are placeholders (`STORE_LISTING.md:18-19`). (e) `STORE_LISTING.md:11` and `:15` set the category to Lifestyle with Health & Fitness secondary. |
| Impact | A wrong Apple "App Privacy" or Google "Data safety" answer is a rejection or takedown risk. Question text sent to a third-party model provider must be disclosed [INF; Apple has tightened rules on sharing personal data with third-party AI, confirm the current text]. Spiritual and mood data can be health-adjacent. |
| Fix | Build one data map from code: Supabase (auth, rows), the backend on Railway, the model provider, Sentry, push providers. Reconcile the three documents to it. Do not publish "no third party" claims. The owner signs the final answers (D-PMOB6). |

### MOB-05 — Cited-clip playback in the native WebView is unproven

| Field | Value |
|---|---|
| Severity | **P1** |
| Type | Unverified assumption |
| Evidence | The default player is `https://www.youtube.com/embed/...&origin=<window.location.origin>` (`CitationCard.tsx:274-276`; `DiscourseAudioStrip.tsx:306-308`). On native, the origin is `https://localhost` (Android, `capacitor.config.ts:8`) or `capacitor://localhost` (iOS, `:9`). The fallback card uses `target="_blank"` (`CitationCard.tsx:258-266`). Capacitor has no `@capacitor/browser` here (MOB-01). `Info.plist` has no `audio` background mode (`:38-41`). No native test exists. [V-STATIC] |
| Impact | Clip playback is the core product (invariant 6: playback window around the verbatim span). If YouTube refuses the embed for a non-HTTP origin, or if `target="_blank"` does nothing in the WebView, the user hears no teacher audio [INF: known to vary by OS and YouTube policy; not tested]. Audio stops when the app goes to the background. |
| Fix | Test the embed on a real Android and iOS device. If it fails, play a direct audio stream for the clip window (the `isDirectVideo` path exists, `CitationCard.tsx:245-255`) or open the clip with `Browser.open`. Decide on background audio (D-PMOB4). Keep the 0.25 s pad (`CLAUDE.md` invariant 6). |
| Verification | `[HUMAN]` device test (AC-MOB-05). |

### MOB-06 — Native build is pinned to the prod Railway URL; the opt-in guard is bypassed

| Field | Value |
|---|---|
| Severity | **P2** |
| Type | Architectural risk |
| Evidence | `backendUrl.ts:36-42` says native builds need `VITE_NATIVE_BACKEND=prod` to reach prod. `.env.mobile:3` sets `VITE_BACKEND_URL` to the prod URL, and `ENV_URL` wins (`backendUrl.ts:47-48`). Railway is stopped (`CLAUDE.md`). `memoryApi.ts:28-31` throws `not_configured` on native when its own URL is empty. |
| Impact | Every `build:mobile` output calls prod, including CI builds (`lint-test.yml:82-83`). There is no staging build variant. Until Railway runs, the native app fails closed on every call. This is the right failure mode, but it is accidental. |
| Fix | Remove the URL from `.env.mobile`. Add `.env.mobile.staging` and `.env.mobile.production` (public values only), selected by a `--mode`. Add one resolver for the voice hook (MOB-03). Add a test that a native build with no URL fails closed. |

### MOB-07 — Push notifications: prompt timing, listener order, token linking

| Field | Value |
|---|---|
| Severity | **P2** |
| Type | Probable defect (three parts) |
| Evidence | (a) The permission prompt fires on mount for every native user, signed in or not, with no explanation (`PushNotificationsManager.tsx:70-73`; mounted `App.tsx:384`). (b) `PushNotifications.register()` runs before the `registration` listener is attached (`:78-86`). The token event can arrive before the listener exists [INF]. (c) `registeredRef` blocks a second registration (`:81-83`). The `Authorization` header is sent only if a session exists (`:39-41`). A token registered before sign-in is never re-sent after sign-in. The backend allows optional auth on `/register` (`backend/app/api/push.py:4`). (d) iOS `aps-environment` is `development` (`App.entitlements:5`) [INF: Xcode release signing normally replaces it; confirm in the archive]. (e) `POST_NOTIFICATIONS` is declared (`AndroidManifest.xml:55`) while D-21 says proactive features are opt-in. |
| Impact | Low opt-in rate, lost tokens, an unlinked device row. A launch-time prompt conflicts with D-21 and with the ethical-retention spec. |
| Fix | Attach listeners before `register()`. Ask for permission only after sign-in and after a plain in-app explanation. Re-register on `SIGNED_IN`. Unregister on sign-out (the key `mg_push_device` exists for this). Gate on the consent scope in the memory spec. Check the entitlement in the archived build. |

### MOB-08 — Release pipeline is a draft: Fastlane, signing, versions, CI

| Field | Value |
|---|---|
| Severity | **P2** |
| Type | Confirmed defect (docs and scripts) |
| Evidence | (a) The Android Fastfile passes `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` as injected signing properties (`mobile/fastlane-android-Fastfile:25-28`). `build.gradle` reads `ANDROID_KEYSTORE_*` and `key.properties`, and throws on `bundleRelease` without them (`build.gradle:9-12,125-137`). The two do not meet. (b) `versionCode 1` is hard-coded (`build.gradle:58`). The Fastfile injects a code from `git rev-list --count` (`:20,29`), which only works if the Gradle build honours that property [INF: unverified]. (c) `key.properties.example:83-84` says the build falls back to debug signing. The build throws instead. (d) Runbook `:73-103` tells the reader to add signing code that already exists. (e) The Fastfiles are not in the native folders; no `Appfile`, `Matchfile` or `Gemfile` is tracked. (f) CI builds only the web bundle (section 2.5). The only native tests are the two template files. |
| Impact | The first release attempt will fail or ship a wrong version code. Nothing in CI catches a broken native project. |
| Fix | Use one set of variable names. Move the Fastfiles under `android/fastlane` and `ios/fastlane` with an `Appfile`. Set versions from one source. Add a CI job: `npm run cap:sync`, `./gradlew assembleDebug lint testDebugUnitTest` on Linux, and an unsigned `xcodebuild` on a macOS runner. Correct the runbook and the example file. |

### MOB-09 — Auto Backup is on and chat history sits in app preferences

| Field | Value |
|---|---|
| Severity | **P2** |
| Type | Architectural risk |
| Evidence | `android:allowBackup="true"` with no rules (`AndroidManifest.xml:5`). Chat history, conversation lists and feedback are written with `Preferences.set` (`chatStorage.ts:11-16`, key list `:25-30`). Where the Supabase session is stored on native was not established: `client.ts:45` uses `brokeredPreviewStorage()` (`previewAuthStorage.ts:41`), which was not read. |
| Impact | On Android, preference files are included in cloud backup and device-to-device transfer. A seeker's private questions leave the device through the backup channel. On iOS the data lives in `UserDefaults`, which is not the Keychain [INF]. |
| Fix | Set `allowBackup="false"`, or add `dataExtractionRules` and `fullBackupContent` that exclude the preference files. Decide whether to keep chat on device at all on native (D-PMOB7). Store auth tokens in secure storage. |

### MOB-10 — Account deletion: reachable, but incomplete for the stores

| Field | Value |
|---|---|
| Severity | **P1** |
| Type | Probable defect (Apple token revocation); Product gap (deletion path) |
| Evidence | Reachable in-app: Profile > `AccountDataCard.tsx:140-190`. "Delete immediately" calls `delete-my-account` (`:171`). The function fails closed when `BACKEND_URL` is unset (`index.ts:46-51`). The other retention options only sign the user out and show a message (`AccountDataCard.tsx:182-190`); whether a server job deletes the account later was not traced (`CancelFlow.tsx` calls `/api/account/*`). The app offers Sign in with Apple through Supabase OAuth (`AuthPage.tsx:598-640`). A repository search for Apple token revocation found no code in `backend`, `supabase` or `src`. [V-STATIC] |
| Impact | Apple requires in-app deletion that starts without a support request, and requires that Sign in with Apple tokens are revoked on deletion [INF; confirm in current App Review Guidelines 5.1.1(v)]. Deletion sits behind a retention funnel that the audit already proposes to remove (D-19). Google Play also requires a web link where a user can ask for deletion, set in the Data safety form [INF]. |
| Fix | Add a visible "Delete my account" action that reaches immediate deletion in two taps, with the retention offer optional. Revoke the Apple token in the edge function (needs the Apple key; owner supplies it). Confirm the scheduled path deletes on a date and show the date. Publish a web deletion URL for Play. Test on a TestFlight build. |

### MOB-11 — Crisis helplines on the device are untested

| Field | Value |
|---|---|
| Severity | **P2** |
| Type | Unverified assumption |
| Evidence | Helplines are `tel:` anchors (`CrisisLines.tsx:16`, `ChatMessage.tsx:1306`) from a list bundled in the app (`crisisHelplines.ts:26-60`), so they show offline. Whether a `tel:` tap opens the dialer from the Capacitor WebView was not tested. A tablet or iPad without a phone does nothing on tap. `config/helplines.yaml` call verification is a separate pending human gate (`CLAUDE.md`, Open work). [V-STATIC] |
| Impact | A seeker in distress may tap a number and nothing happens. This is a safety path. The static list covers India and the US only. |
| Fix | Test `tel:` on one Android phone, one iPhone and one tablet. Show the number as plain text next to the link. Keep the helplines on the first screen of the crisis response. Add a native smoke check to the pre-release list. Region choice for other countries stays a human decision. |

### MOB-12 — Offline and cold-start behaviour is unverified

| Field | Value |
|---|---|
| Severity | **P2** |
| Type | Unverified assumption |
| Evidence | The runbook checklist item "App does not crash on cold launch with no network" is unchecked (`MOBILE_RELEASE_RUNBOOK.md:252`). The bundle is local (no `server.url`), so the shell loads offline. Chat needs the backend. The error cards and the crisis response when offline were not traced. The audit already records that a cut stream leaves teacher text unlabelled (`16-root-cause-and-failure-register.md:187`). |
| Fix | Test airplane-mode launch and a mid-stream drop on both OSes. Show a clear offline card with the bundled helplines. |

### MOB-13 — Deep links use a custom scheme only

| Field | Value |
|---|---|
| Severity | **P3** |
| Type | Architectural risk |
| Evidence | `autoVerify="false"` (`AndroidManifest.xml:25`). No `assetlinks.json` or `apple-app-site-association` is tracked. No Associated Domains entitlement (`App.entitlements:1-8`). The `appUrlOpen` listener exists only while `AuthPage` is mounted (`AuthPage.tsx:160-197`). There is no `getLaunchUrl` call. |
| Impact | Another Android app can register the same scheme. PKCE limits the harm because the code needs the stored verifier [INF]. If the callback arrives when `AuthPage` is not mounted, sign-in does not finish. |
| Fix | Move the listener to a root component. Call `App.getLaunchUrl()` once at start. Add verified App Links and Universal Links only if the owner wants web-to-app links (D-PMOB5). |

### MOB-14 — A second mobile codebase exists

| Field | Value |
|---|---|
| Severity | **P3** |
| Type | Architectural risk |
| Evidence | `mobile/expo/` (Expo SDK 54 companion). Audit item N-03 (`19-...md:84`) recommends choosing one. The Expo README lists signing and permissions as unfinished (`mobile/expo/README.md:3`). |
| Fix | Decide per D-PMOB1. Freeze the one not chosen. |

### MOB-15 — Smaller native hygiene items

| Field | Value |
|---|---|
| Severity | **P3** |
| Type | Unverified assumption |
| Evidence | (a) `UIRequiredDeviceCapabilities = armv7` (`Info.plist:50-53`) is the old Capacitor template value. (b) `file_paths.xml:3` exposes the whole external storage root to the FileProvider (the provider is not exported, `AndroidManifest.xml:37`). (c) `targetSdk 36` enforces edge-to-edge layout on Android 15 and later [INF]; no layout test exists. (d) 16 KB page-size support is unknown (no native libraries are tracked; the plugins' libraries were not inspected). (e) The App Store icon set holds one 512 px image (`AppIcon-512@2x.png`); the 1024 px marketing icon was not checked. |
| Fix | Review each item at the first archive. Narrow `file_paths.xml`. Drop `armv7`. |

### 3.1 Severity summary

| Severity | IDs |
|---|---|
| P0 | none |
| P1 | MOB-01, MOB-02, MOB-03, MOB-04, MOB-05, MOB-10 |
| P2 | MOB-06, MOB-07, MOB-08, MOB-09, MOB-11, MOB-12 |
| P3 | MOB-13, MOB-14, MOB-15 |

---

## 4. Store-readiness checklist

Status words: **Ready** (evidence shows it done), **Requires implementation** (code or file change), **Requires owner** (decision or legal input), **Requires store console** (an account holder acts in the console). "Ready" here means the repository part only. Nothing was tested on a device or in a console.

| # | Item | Store | Status | Evidence |
|---|---|---|---|---|
| 1 | Developer accounts (Play $25, Apple $99/yr, D-U-N-S for an organisation) | Both | Requires owner | Runbook `:13-22`. No evidence an account exists. |
| 2 | Account deletion inside the app | Apple 5.1.1(v), Play | Requires implementation | MOB-10. Path exists (`AccountDataCard.tsx:140-190`); revocation and a two-tap path are missing. |
| 3 | Web deletion URL for Play Data safety | Play | Requires implementation, then store console | Not found in the repository. |
| 4 | Sign in with Apple when other social login is offered | Apple 4.8 | Requires implementation | Button exists (`AuthPage.tsx:1031-1052`). Provider setup is unchecked in the runbook (`:242`). Works only if MOB-01 is fixed. |
| 5 | Google sign-in works in the app | Both | Requires implementation | MOB-01. |
| 6 | Privacy manifest | Apple | Requires implementation | MOB-02. File absent. |
| 7 | App Privacy ("nutrition") labels | Apple | Requires owner, then store console | `STORE_LISTING.md:186-202` is a draft and is inaccurate (MOB-04). |
| 8 | Data safety form | Play | Requires owner, then store console | `STORE_LISTING.md:206-216`; MOB-04. |
| 9 | Privacy policy at a public HTTPS URL | Both | Requires owner | URL is a placeholder (`STORE_LISTING.md:18`). Policy text not reviewed here. |
| 10 | Permission justification: Android | Play | Requires implementation | `POST_NOTIFICATIONS` declared; microphone missing (MOB-03, MOB-07). |
| 11 | Permission justification: iOS usage strings | Apple | Requires implementation | No `NS*UsageDescription` (`Info.plist`); MOB-03. |
| 12 | Target SDK | Play | Ready in repo; confirm in console | `targetSdk 36` (`variables.gradle:4`). Play's current minimum was not fetched. |
| 13 | Minimum OS | Both | Ready | Android 24 (`variables.gradle:2`); iOS 15 (`project.pbxproj:235`). |
| 14 | Current Xcode / SDK for upload | Apple | Requires store console | Not checkable here. Confirm at first archive. |
| 15 | Release signing: Android | Play | Requires implementation, then owner | Gradle code exists. Fastlane mismatch (MOB-08). The owner creates and backs up the key. Play App Signing enrolment is a console step. |
| 16 | Release signing: iOS | Apple | Requires owner | Automatic signing, no team set (`project.pbxproj:301`). |
| 17 | No secrets committed | Both | Ready | Section 2.2. Only `key.properties.example` with placeholders is tracked. Secret scan of history was not run here. |
| 18 | Cleartext and ATS | Both | Ready | No cleartext flag on Android; no ATS exceptions on iOS. All URLs in `backendUrl.ts` are HTTPS. |
| 19 | Push credentials (FCM file, APNs key) | Both | Requires owner | Both are ignored files. Backend env vars per runbook `:176-203`. |
| 20 | Production push entitlement | Apple | Requires implementation | `aps-environment = development` (`App.entitlements:5`); MOB-07. |
| 21 | Content rights for teacher audio and text | Both | Requires owner | `docs/PROD_READY_CHECKLIST.md` and `14c-content-permissions-and-ip-register.md` hold the register. The rights letter from Ekam or OWA is deferred by the owner (`CLAUDE.md`, "Before going public"). Do not raise it as a blocker before the owner announces going public. |
| 22 | Health and crisis content rules | Both | Requires owner, then store console | Secondary category Health & Fitness (`STORE_LISTING.md:15`). Play has a Health apps declaration form [INF]. The app gives no medical advice and shows helplines. Clinician and native-speaker reviews are pending human gates (`CLAUDE.md`). |
| 23 | Helplines work on device | Both | Requires implementation (test) | MOB-11. |
| 24 | Age rating and target audience | Both | Requires owner, then store console | Listing says 18+ (`STORE_LISTING.md:21`). Questionnaires are console steps. The audit's age-gate finding is outside this document. |
| 25 | Screenshots and listing text | Both | Requires owner | `docs/store_screenshots/` does not exist. Generator: `scripts/ops/generate_store_screenshots.cjs` [name from runbook, not checked]. |
| 26 | Closed-test requirement for new Play personal accounts | Play | Requires store console | Runbook `:138` (20 testers, 14 days). Applies only to personal accounts [INF]. |
| 27 | Encryption export answer | Apple | Ready (draft) | `ITSAppUsesNonExemptEncryption=false` (`Info.plist:36-37`). The owner confirms. |
| 28 | Review demo account | Apple | Requires owner | Runbook `:158`. |

---

## 5. How mobile fits the release gates

Gate names follow `FINAL_DECISION_AND_RISK_REGISTER.md` section 2: Gate A is Railway staging. Gate B is production for invited users. Gate C is public release.

| Question | Answer |
|---|---|
| Does mobile block Gate A? | **No.** Staging is a web and API gate. The native apps need Railway running first (section 0, rule 5). |
| Does mobile block Gate B? | **No**, provided no store build (TestFlight, Play internal or closed testing) is given to invited users as part of Gate B. If the owner wants invited users on a store test track, treat that as Gate B scope and require MOB-01, MOB-03, MOB-04, MOB-05 and MOB-10 first (D-PMOB8). |
| Where does mobile belong? | **Gate C or later.** Public store listing needs all P1 findings closed and the section 4 items done. |
| Does mobile change any web gate? | No. The only shared code is `backendUrl.ts`, `AuthPage.tsx`, `PushNotificationsManager.tsx`, `chatStorage.ts`. Changes there need the web tests to pass (AC-MOB-09). |
| Does a mobile build ship teacher words? | It bundles no teacher text. Clips load from the backend. The first-person invariants (verbatim only, label "Related, not a direct answer" while no calibration profile exists) are unchanged and must hold on mobile (AC-MOB-10). |

---

## 6. Acceptance criteria

Tests marked `[HUMAN]` need a macOS machine, a device or a store console. No such test was run for this document.

| ID | Criterion | Test | Pass condition |
|---|---|---|---|
| AC-MOB-01 | Google and Apple sign-in complete on native (MOB-01) | `[HUMAN]` on one Android phone and one iPhone, release-like build. Unit test for the OAuth call options. | The system browser opens. The app returns on `appUrlOpen`. The user lands on `/chat`. Unit test asserts `skipBrowserRedirect: true` and a `Browser.open` call on native. |
| AC-MOB-02 | Privacy manifest is present and valid (MOB-02) | A file-exists check in CI plus Xcode privacy report `[HUMAN]` | `ios/App/App/PrivacyInfo.xcprivacy` is tracked. The report lists no undeclared required-reason API. |
| AC-MOB-03 | Microphone is either complete or hidden (MOB-03) | Manifest and plist check in CI. `[HUMAN]` device check. | If voice ships: both permission entries exist, the prompt appears at first tap, a denied prompt shows a clear message. If not: no mic control renders when `isNativePlatform()` is true. |
| AC-MOB-04 | Privacy statements match the code (MOB-04) | Review against a written data map. | Every third party in code appears in the data map and in both store drafts. The owner signs the final text. |
| AC-MOB-05 | A cited clip plays on both OSes (MOB-05) | `[HUMAN]` device test with three citations: one short, one near the end of a video, one direct stream. | Audio starts within the span (start minus 0.25 s to end plus 0.25 s). The user can open the source if embed fails. |
| AC-MOB-06 | Native builds select the backend by mode (MOB-06) | Unit test of `backendUrl.ts`. Build log check. | With no URL, calls fail closed. A staging build never contains the prod URL. |
| AC-MOB-07 | Push is opt-in and linked (MOB-07) | Unit test with a mocked plugin. `[HUMAN]` real-device push. | No prompt before sign-in. Listeners are attached before `register()`. A token is sent after `SIGNED_IN`. Sign-out removes it. |
| AC-MOB-08 | Release build is reproducible (MOB-08) | New CI job. | `assembleDebug`, lint and unit tests pass on Linux. An unsigned iOS archive builds on macOS. Versions come from one source. |
| AC-MOB-09 | Web behaviour is unchanged | Existing web unit and e2e suites. | No new failure. |
| AC-MOB-10 | Safety and voice invariants hold on mobile | `[HUMAN]` crisis prompt on device; existing safety scenarios. | A crisis phrase shows the helpline block with working `tel:` links. A teacher clip carries its label and speaker. No first-person teacher voice appears. |
| AC-MOB-11 | Backup excludes private data (MOB-09) | Manifest check in CI. | `allowBackup="false"` or exclusion rules cover the preference files. |
| AC-MOB-12 | Account deletion meets store rules (MOB-10) | `[HUMAN]` on TestFlight and Play internal. | Two taps reach deletion. The auth user and the Apple token are gone. The app signs out. Re-login fails. |
| AC-MOB-13 | Offline start is safe (MOB-12) | `[HUMAN]` airplane-mode launch. | No crash. An offline card appears with helplines. |

---

## 7. Ordered tasks

Each task is one PR. Order is by dependency. None of these tasks is started by this document.

| ID | Task | Files | Depends on | Non-goals | Rollback |
|---|---|---|---|---|---|
| NEW-MOB-1 | Decide scope: Capacitor or Expo, voice in v1, background audio, native Apple sign-in (D-PMOB1 to D-PMOB4). | `docs/` decision record | Owner | No code | None needed |
| NEW-MOB-2 | Reconcile docs: correct runbook, `MOBILE_DEPLOY_CONFIDENCE.md`, `STORE_LISTING.md`, `key.properties.example` against this review. | The four files | None | No store submission | Revert the doc commit |
| NEW-MOB-3 | Mode-based backend URL; remove prod URL from `.env.mobile`; one URL resolver for the voice hook (MOB-06). | `src/lib/backendUrl.ts`, `.env.mobile`, new `.env.mobile.*`, `src/hooks/useVoiceInput.ts`, tests | None | No backend change | Restore `.env.mobile` |
| NEW-MOB-4 | OAuth through the system browser (MOB-01). | `package.json`, `src/pages/AuthPage.tsx`, `src/lib/authConstants.ts`, tests; Supabase redirect list (owner) | NEW-MOB-3 | No change to web OAuth path | Feature flag off by platform check; revert PR |
| NEW-MOB-5 | Privacy manifest and usage strings; microphone decision applied (MOB-02, MOB-03). | `ios/App/App/PrivacyInfo.xcprivacy`, `Info.plist`, `AndroidManifest.xml`, `useSpeechRecognition.ts` callers | NEW-MOB-1 | No new permissions beyond the decision | Revert PR |
| NEW-MOB-6 | Backup rules and storage review (MOB-09). | `AndroidManifest.xml`, new `res/xml/*`, `chatStorage.ts` | NEW-MOB-1 | No change to web storage | Revert PR |
| NEW-MOB-7 | Push opt-in, listener order, token linking, entitlement check (MOB-07). | `PushNotificationsManager.tsx`, `PushPermissionPrompt.tsx`, `App.entitlements`, tests | Memory spec consent scopes (NEW-MEM series) | No new push content types | Disable the manager by flag |
| NEW-MOB-8 | Clip playback on native: device test, then fallback player or `Browser.open` (MOB-05). | `CitationCard.tsx`, `DiscourseAudioStrip.tsx`, tests | NEW-MOB-4 (Browser plugin) | No change to the pad or span logic | Revert PR |
| NEW-MOB-9 | Account deletion: two-tap path, Apple token revocation, web deletion URL (MOB-10). | `AccountDataCard.tsx`, `CancelFlow.tsx`, `supabase/functions/delete-my-account/index.ts` | D-19, owner supplies the Apple key | No retention redesign beyond making it optional | Edge function version rollback |
| NEW-MOB-10 | Helpline `tel:` and offline card checks; native smoke list (MOB-11, MOB-12). | `CrisisLines.tsx`, `ChatMessage.tsx`, test docs | NEW-MOB-8 | No change to helpline content or order | Revert PR |
| NEW-MOB-11 | Release pipeline: Fastlane location and names, one version source, CI job for native builds (MOB-08). | `mobile/` Fastfiles, `android/app/build.gradle`, `.github/workflows/` | NEW-MOB-2 | No signing keys in CI before the owner adds secrets | Remove the workflow file |
| NEW-MOB-12 | Deep-link hardening and hygiene (MOB-13, MOB-15). | `App.tsx`, `AuthPage.tsx`, `file_paths.xml`, `Info.plist` | NEW-MOB-4 | No Universal Links unless D-PMOB5 | Revert PR |
| NEW-MOB-13 | Store paperwork: labels, Data safety, health declaration, screenshots, test tracks. | Console only; `docs/STORE_LISTING.md` | NEW-MOB-2, NEW-MOB-5, NEW-MOB-9 | No submission until D-PMOB8 | Withdraw drafts in the console |

---

## 8. Open questions

| ID | Question | Why it matters | Recommended | Alternative | Tasks |
|---|---|---|---|---|---|
| PROPOSED D-PMOB1 | Keep Capacitor as the only mobile client and freeze `mobile/expo/` (audit N-03)? | Two clients double the release work. | Yes. The Capacitor projects are further along. | Choose Expo and drop `android/`, `ios/`. Not recommended: more rework. | NEW-MOB-1, MOB-14 |
| PROPOSED D-PMOB2 | Use native Sign in with Apple, or keep the web OAuth flow? | Native flow is more reliable inside the app and revokes more cleanly. | Native flow, after MOB-01 is fixed for Google. | Web flow through the system browser. Simpler, but less tested on iOS. | NEW-MOB-4 |
| PROPOSED D-PMOB3 | Ship voice input in v1? | It needs permissions, a backend STT path and review notes. | No for v1. Hide it on native. | Ship with full permission flow. | NEW-MOB-5 |
| PROPOSED D-PMOB4 | Support background audio for clips? | Needs the iOS `audio` mode and a native-grade player. | No for v1. Foreground playback only. | Add background audio later. | NEW-MOB-8 |
| PROPOSED D-PMOB5 | Add Universal Links and App Links? | Needs a domain file and entitlements. | No for v1. Custom scheme with PKCE is enough. | Add verified links. | NEW-MOB-12 |
| PROPOSED D-PMOB6 | Who signs the store privacy answers, and on what data map? | A wrong answer risks takedown. | The owner, after MOB-04 reconciliation. | Delegate to a privacy reviewer. | NEW-MOB-2, NEW-MOB-13 |
| PROPOSED D-PMOB7 | Keep local chat history on native, or keep it on the server only? | Backup and device-theft exposure. | Keep on device with backup excluded and a clear-data control. | Server only. More private on device, needs the network. | NEW-MOB-6 |
| PROPOSED D-PMOB8 | May invited users get a TestFlight or Play internal build before Gate C? | It moves mobile into Gate B scope. | No. Keep mobile at Gate C. | Yes, after MOB-01, 03, 04, 05, 10 close. | Section 5 |

Existing decisions touched: D-19 (delete the churn funnel, MOB-10), D-21 (proactive features opt-in, MOB-07), D-22 (native review scope), N-03 (MOB-14).

---

## 9. Verified, assumptions, unknowns

### Verified (read at `fb5cab0f`)

- Capacitor 8 packages, plugin list, app id and config (`package.json`, `capacitor.config.ts`).
- Android: SDK levels, version 1/1.0.0, permissions, `allowBackup`, custom-scheme filter, signing code and its failure behaviour, ignore rules.
- iOS: deployment target 15.0, bundle id, version 1.0/1, automatic signing with no team, no privacy manifest, no usage strings, `aps-environment = development`, no ATS exception.
- No signing material is tracked. Only `key.properties.example` with placeholders.
- Backend URL logic, `.env.mobile` content, OAuth calls without a system browser, push manager logic, chat storage on `Preferences`, YouTube embed code, microphone code, helpline links, deletion UI and edge function guard.
- CI builds the mobile web bundle only.

### Assumptions

- Capacitor's Android WebView and iOS WKWebView behave as the public docs describe (the `Preferences` plugin uses `UserDefaults` and `SharedPreferences`; the WebView loads `supabase-js` OAuth in place) [INF].
- Google blocks OAuth in embedded WebViews; Apple requires a privacy manifest, usage strings, in-app deletion and Sign in with Apple token revocation; Play requires a recent target SDK and a Data safety form [INF from general knowledge; no store page was fetched].
- The owner has no store accounts yet (nothing in the repository shows one).

### Unknowns

- Whether any native build has ever run on a device or emulator. No evidence in the repository.
- Whether YouTube embeds play with the `https://localhost` and `capacitor://localhost` origins.
- Where the Supabase session is stored on native (`previewAuthStorage.ts` was not read).
- Whether `useVoiceInput` and the mic button render on native.
- Whether the scheduled-deletion path deletes data later.
- The current Apple and Google rule text and minimum SDK dates.
- Plugin-level privacy manifests and native-library page-size support.
- Whether Railway will host the backend for mobile, and when.


---

## 10. Mobile-viewport web proxy and owner-run native test checklist (2026-11-06)

**This is a proxy.** What ran is the **web app in a mobile-sized Chromium window**, with the Playwright device descriptors for Pixel 7 and iPhone 14. It is **not** the Capacitor native shell, **not** a phone, and **not** WebKit. No Android SDK, emulator, KVM or macOS was available, and none was installed. No native result in this spec (MOB-01 to MOB-15) is confirmed or cleared by this section. Every native item stays `[HUMAN]` and UNPROVEN until the owner runs 10.3. Full accessibility detail is in section 10 of `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md`.

### 10.1 What ran

Pages: `/`, `/auth`, `/chat`, `/practices` (4 of 4 reached; no backend; placeholder Supabase values). Devices: `devices['Pixel 7']` (412x839) and `devices['iPhone 14']` (390x664), both Chromium with touch and a mobile user agent. Dev server and script commands are listed in section 10.1 of the accessibility spec; the server was stopped afterwards (curl returned 000). No file under `src/`, tests, config or packages was changed.

| Check | Pixel 7 | iPhone 14 | Reading |
|---|---|---|---|
| Elements under 24 px (measured with `getBoundingClientRect`, includes the 1x1 skip link) | `/` 19, `/auth` 8, `/chat` 3, `/practices` 11 | `/` 19, `/auth` 7, `/chat` 3, `/practices` 11 | Matches A11Y-09. Examples: slide dots 8x8, Show password 16x16, footer and legal links 13 to 18 px high, "Details" 40x16. |
| Cookie banner overlaps the Send button on `/chat` | Yes. Send centre (361,707) returns the dialog. Banner top 704, 123 px high. | Yes. Send centre (339,532) returns the dialog. Banner top 529, 123 px high (about 18% of the viewport). | Confirms A11Y-11 on two phone sizes. Textarea is not covered. |
| Viewport meta | `width=device-width, initial-scale=1.0, viewport-fit=cover, maximum-scale=5.0` | same | Pinch zoom allowed. |
| Safe-area / `dvh` rules in the CSS | `safe-area-inset` and `dvh` both present | same | Headless Chromium reports zero insets, so notch and home-indicator clearance is UNPROVEN. |
| Horizontal scroll | none on any page | none on any page | |
| Console errors per page load | `/` 7, `/auth` 3, `/chat` 18, `/practices` 6 | `/` 6, `/auth` 3, `/chat` 18, `/practices` 6 | Mostly set-up noise: 502 from the dev proxy, refused Supabase URL and WebSocket, Google script origin message, React dev warnings, one uncaught rejection on `/auth` ("Error: Ya"). |

What this tells the owner: the web layout holds at 390 and 412 px without sideways scroll, small targets and the banner overlap reproduce on phone-sized viewports, and the page boots without a backend. What it cannot tell: anything about the WebView, OAuth, microphone, clip playback, deletion, `tel:` links, offline start, push, or screen readers.

### 10.2 How to use the checklist

Run each block on one Android phone and one iPhone with a release-like build (`MOBILE_RELEASE_RUNBOOK.md`, build commands) pointing at a staging backend with a test account. Do not use a production account. Do not call 112 or any real emergency number; use a number from `crisisHelplines.ts` only to see that the dialer opens, and cancel before the call connects. Record the build number, OS version and device in the header row. A box is ticked only by the person who ran the step.

Header: Build ____  Date ____  Tester ____  Android device/OS ____  iPhone/OS ____

### 10.3 Owner-run native test checklist

**MOB-01: OAuth in the system browser** (AC-MOB-01; finding says the code runs OAuth in the WebView)

| # | Step | Expected result | Android | iOS |
|---|---|---|---|---|
| 1.1 | Fresh install. Open Sign in. Tap "Continue with Google". | The system browser (Custom Tab or SFSafariViewController) opens. The address bar shows Google. No Google page loads inside the app. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 1.2 | Finish Google sign-in with the test account. | The app returns on its own. The user lands on `/chat`, signed in. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 1.3 | Repeat 1.1 and 1.2 for "Continue with Apple" (iOS) and for Apple if offered on Android. | Same as 1.1 and 1.2, or the button is absent by design. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 1.4 | Start Google sign-in, then close the browser without finishing. | The app stays on the sign-in screen with no stuck spinner ("Connecting to Google..." goes away). | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 1.5 | Sign in with email and password. | Signs in (this path is not affected by MOB-01). | [ ] pass [ ] fail | [ ] pass [ ] fail |

**MOB-03: Microphone permission** (AC-MOB-03)

| # | Step | Expected result | Android | iOS |
|---|---|---|---|---|
| 3.1 | Open `/chat`. Do not tap the microphone. Check Settings > App > Permissions. | No microphone prompt at launch. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 3.2 | Tap "Start voice input" (if shown). | A system prompt with a plain reason appears at this first tap. If voice is not shipped in v1, no microphone control is shown at all. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 3.3 | Allow. Speak a short sentence. | Text appears in the composer, or a clear message says why not. The app does not crash. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 3.4 | Deny in a fresh install, then tap the control again. | A clear message explains how to enable the microphone. No silent failure. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 3.5 | (Reviewer) Check the build: `RECORD_AUDIO` in the Android manifest; `NSMicrophoneUsageDescription` in `Info.plist`. | Present if the control ships; the control is hidden if they are absent. | [ ] pass [ ] fail | [ ] pass [ ] fail |

**MOB-05: Clip playback** (AC-MOB-05; use three clips: a short one, one near the end of a video, one direct stream if available)

| # | Step | Expected result | Android | iOS |
|---|---|---|---|---|
| 5.1 | Ask a question that returns a clip. Open the clip. | The clip window opens. Audio or video starts within the span (start minus 0.25 s to end plus 0.25 s). | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 5.2 | Repeat for the clip near the end of its video. | Plays to the end of the span and stops; no long tail from the host. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 5.3 | Rotate the phone during playback. Lock and unlock the screen. | Playback state is sensible; the app does not crash. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 5.4 | Turn off the network, then open a clip. | A clear message and a way to open the source link; no blank player. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 5.5 | If the embed does not start (YouTube refuses `https://localhost` or `capacitor://localhost`), note it. | A fallback "open the source" action exists. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 5.6 | Check the verbatim text beside the player matches what is said. | Text equals the spoken span. | [ ] pass [ ] fail | [ ] pass [ ] fail |

**MOB-10: Account deletion and Apple token revocation** (AC-MOB-10 area; use a throwaway account)

| # | Step | Expected result | Android | iOS |
|---|---|---|---|---|
| 10.1 | Sign in with a throwaway account (email). Go to Profile and find "Delete my account". | Reachable without contacting support. Count the taps from Profile. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 10.2 | Choose immediate deletion. Count taps. | Two taps or fewer to reach the final confirm, with any retention offer optional (spec target). | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 10.3 | Confirm. Then try to sign in again with the same account. | Sign-in fails; the user is signed out of the app at once. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 10.4 | iOS only: create a throwaway account with Sign in with Apple. Delete it. Then open Settings > Apple ID > Sign-In & Security > Sign in with Apple. | The app is gone from that list (token revoked). If it is still listed, mark fail. | n/a | [ ] pass [ ] fail |
| 10.5 | If deletion is scheduled for a later date, check the date shown. | The date is shown and the account is gone on that date. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 10.6 | Offline: start deletion with no network. | A clear error. The account is NOT reported as deleted. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 10.7 | Ask the backend owner to confirm the user's rows are gone (server side, not in this checklist's reach). | Confirmed by the owner. | [ ] pass [ ] fail | [ ] pass [ ] fail |

**MOB-11: Helpline `tel:` links** (safety path; one phone, one tablet)

| # | Step | Expected result | Android | iOS |
|---|---|---|---|---|
| 11.1 | Open the first-run safety notice (fresh install) and tap a helpline number. | The dialer opens with the number filled in. Cancel before the call connects. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 11.2 | Trigger the error card (airplane mode, send a question) and tap the Tele-MANAS line. | Same as 11.1. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 11.3 | Repeat 11.1 on a tablet or an iPad without a phone. | Nothing breaks. The number is also shown as plain text so it can be read out. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 11.4 | Check the number on screen against `src/lib/crisisHelplines.ts`. | They match. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 11.5 | Do NOT dial 112 or any emergency number. | n/a | n/a | n/a |

**MOB-12: Offline and cold start**

| # | Step | Expected result | Android | iOS |
|---|---|---|---|---|
| 12.1 | Force-close the app. Turn on airplane mode. Launch. | The app opens with no crash and no blank screen. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 12.2 | Send a question offline. | A clear offline message that shows the bundled helplines. No spinner that never ends. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 12.3 | Send a question, then switch to airplane mode while the answer loads. | A clear failure, not a half answer with unlabelled teacher text. | [ ] pass [ ] fail | [ ] pass [ ] fail |
| 12.4 | Turn the network back on. Tap retry. | The question goes through. | [ ] pass [ ] fail | [ ] pass [ ] fail |

**TalkBack (Android) and VoiceOver (iOS) basics.** These are the screen-reader checks this proxy could not run. Turn the screen reader on, then use swipe-right (next) and swipe-left (previous). Write what is spoken.

| # | Step | Expected result | Heard (write it) | Android | iOS |
|---|---|---|---|---|---|
| S.1 | Open `/chat`. Swipe through the page from the top. | Order: skip link, heading "Chat with your AI Spiritual Guide", then the sidebar or menu, greeting, composer ("Your message"), language, More actions, Start voice input, Send. No unnamed "button". | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.2 | Note any element read as "graphic" or "image" with no name. | Few or none (the web tree lists many unnamed icons; A11Y-19). | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.3 | Type a question and send it. | The answer's arrival is announced (A11Y-13), for example "Answer ready" or "No teaching matched". Focus does not drop to the page top (A11Y-08). | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.4 | Swipe through an answer that has a clip. | Order is sensible: the assistant's own labelled text, the teacher label and the speaker name, then the verbatim quote, then the source and the play control. The quote is announced as the teacher's words, and the speaker name is spoken. | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.5 | Find the "Related, not a direct answer" label. | The exact words are spoken, once, next to the answer. The reason for "related" or "unverified" is reachable (A11Y-04), not only on hover. | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.6 | Open the clip window. | Spoken as a dialog with a name (A11Y-05). The close control is named. Focus returns to the clip button on close. | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.7 | Choose Hindi or Telugu as the language, then open an English quote. | The quote is read with a suitable voice, not garbled (A11Y-07). | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.8 | Trigger the error card (offline) and listen. | The error is announced without moving focus; the helpline line is read in full. | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.9 | Find the helpline link in the first-run notice and in the error card. | Spoken as a link with the number, for example "Tele-MANAS, 14416". Double-tap opens the dialer. | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |
| S.10 | With the cookie banner visible, reach Send by swiping and double-tap it. | Send works with the banner on screen (A11Y-11 shows a touch tap on Send may hit the banner in the web view). | ______ | [ ] pass [ ] fail | [ ] pass [ ] fail |

### 10.4 Boundaries of this section

- A tick in a pass box closes nothing in the findings register by itself. The owner updates MOB-01, MOB-03, MOB-05, MOB-10, MOB-11 and MOB-12 after the run, with the build and device recorded.
- Items S.1 to S.10 depend on text that does not render without a backend. The owner needs a staging backend and a test account to get an answer, a clip and the "Related, not a direct answer" label.
- Store readiness (section 4) stays NOT met until the P1 items pass on real devices.
