# Internationalization (I18N) Gap Analysis Report

This report identifies hardcoded English strings in key user-facing components that should be routed through `i18next`'s `t()` function.

## 1. Profile & Settings
High concentration of hardcoded labels, descriptions, and empty states.

- `src/pages/ProfilePage.tsx:406` — "Conversations" — `profile.tabs.conversations`
- `src/pages/ProfilePage.tsx:407` — "Profile" — `profile.tabs.profile`
- `src/pages/ProfilePage.tsx:408` — "Insights" — `profile.tabs.insights`
- `src/pages/ProfilePage.tsx:409` — "Notes" — `profile.tabs.notes`
- `src/pages/ProfilePage.tsx:410` — "Memory" — `profile.tabs.memory`
- `src/pages/ProfilePage.tsx:411` — "Settings" — `profile.tabs.settings`
- `src/pages/ProfilePage.tsx:412` — "Support" — `profile.tabs.support`
- `src/pages/ProfilePage.tsx:419` — "Personal Details" — `profile.personalDetails.title`
- `src/pages/ProfilePage.tsx:420` — "Tell the Guru about yourself." — `profile.personalDetails.subtitle`
- `src/pages/ProfilePage.tsx:450` — "Display Name" — `profile.personalDetails.displayName`
- `src/pages/ProfilePage.tsx:468` — "Your Path & Intention" — `profile.personalDetails.bio`
- `src/pages/ProfilePage.tsx:484` — "Preferred Language" — `profile.personalDetails.language`
- `src/pages/ProfilePage.tsx:499` — "Guru's Tone" — `profile.personalDetails.tone`
- `src/pages/ProfilePage.tsx:520` — "Unsaved changes..." — `profile.personalDetails.unsavedChanges`
- `src/pages/ProfilePage.tsx:539` — "Activity Summary" — `profile.activitySummary.title`
- `src/pages/ProfilePage.tsx:540` — "Your interactions with the Guru." — `profile.activitySummary.subtitle`
- `src/pages/ProfilePage.tsx:549` — "Conversations started" — `profile.activitySummary.conversationsStarted`
- `src/pages/ProfilePage.tsx:558` — "Meditation practices" — `profile.activitySummary.meditations`
- `src/pages/ProfilePage.tsx:596` — "Recent Insights" — `profile.insights.title`
- `src/pages/ProfilePage.tsx:597` — "Patterns woven from your practice, mood, and conversations." — `profile.insights.subtitle`
- `src/pages/ProfilePage.tsx:619` — "No insights yet. Continue your practices to reveal your spiritual patterns." — `profile.insights.empty`
- `src/pages/ProfilePage.tsx:636` — "Conversations" — `profile.conversations.title`
- `src/pages/ProfilePage.tsx:637` — "Manage and prune your chat history." — `profile.conversations.subtitle`
- `src/pages/ProfilePage.tsx:642` — "Keep conversations for" — `profile.conversations.keepFor`
- `src/pages/ProfilePage.tsx:690` — "No conversations." — `profile.conversations.empty`
- `src/pages/ProfilePage.tsx:709` — "Delete all conversations" — `profile.conversations.deleteAll`
- `src/pages/ProfilePage.tsx:713` — "Delete all conversations?" — `profile.conversations.confirmDeleteTitle`
- `src/pages/ProfilePage.tsx:715` — "Type DELETE to confirm. This action cannot be undone." — `profile.conversations.confirmDeleteMessage`
- `src/pages/ProfilePage.tsx:722` — "Cancel" — `common.cancel`
- `src/pages/ProfilePage.tsx:735` — "Confirm" — `common.confirm`
- `src/pages/ProfilePage.tsx:752` — "Appearance" — `profile.appearance.title`
- `src/pages/ProfilePage.tsx:753` — "Customize the interface theme." — `profile.appearance.subtitle`
- `src/pages/ProfilePage.tsx:781` — "Voice & Audio" — `profile.audio.title`
- `src/pages/ProfilePage.tsx:782` — "Configure Text-to-Speech playback." — `profile.audio.subtitle`
- `src/pages/ProfilePage.tsx:787` — "Enable Guru Voice" — `profile.audio.enableVoice`
- `src/pages/ProfilePage.tsx:788` — "Read teachings aloud automatically" — `profile.audio.enableVoiceSubtitle`
- `src/pages/ProfilePage.tsx:799` — "Speech Rate" — `profile.audio.speechRate`
- `src/pages/ProfilePage.tsx:811` — "Guru Voice (Mayura)" — `profile.audio.voiceName`
- `src/pages/ProfilePage.tsx:812` — "Choose the voice personality for Indic language audio." — `profile.audio.voiceSubtitle`
- `src/pages/ProfilePage.tsx:834` — "Reminders" — `profile.reminders.title`
- `src/pages/ProfilePage.tsx:835` — "Stay consistent with your spiritual goals." — `profile.reminders.subtitle`
- `src/pages/ProfilePage.tsx:844` — "Daily notification to find your center" — `profile.reminders.dailySubtitle`
- `src/pages/ProfilePage.tsx:868` — "Scheduled for" — `profile.reminders.scheduledFor`
- `src/pages/ProfilePage.tsx:900` — "Export your data, or permanently delete your account." — `profile.danger.subtitle`
- `src/pages/ProfilePage.tsx:942` — "Clear local data?" — `profile.danger.clearLocalData`
- `src/pages/ProfilePage.tsx:1033` — "Contact Support" — `profile.support.title`
- `src/pages/ProfilePage.tsx:1044` — "Message sent!" — `profile.support.success`
- `src/pages/ProfilePage.tsx:1056` — "Name (optional)" — `profile.support.name`
- `src/pages/ProfilePage.tsx:1060` — "Your Email" — `profile.support.email`
- `src/pages/ProfilePage.tsx:1067` — "Category" — `profile.support.category`
- `src/pages/ProfilePage.tsx:1073` — "Subject" — `profile.support.subject`
- `src/pages/ProfilePage.tsx:1079` — "Message" — `profile.support.message`
- `src/pages/ProfilePage.tsx:1084` — "Attachments" — `profile.support.attachments`
- `src/components/profile/MemoryManager.tsx:546` — "Consciousness Map" — `profile.memory.mapTitle`
- `src/components/profile/MemoryManager.tsx:560` — "State Insights" — `profile.memory.stateInsights`
- `src/components/profile/MemoryManager.tsx:570` — "Drag to pan · Scroll to zoom" — `profile.memory.help`
- `src/components/profile/MemoryManager.tsx:611` — "Your Consciousness Map" — `profile.memory.heading`
- `src/components/profile/MemoryManager.tsx:613` — "Every dialogue, reflection, and question you share..." — `profile.memory.description`

## 2. Knowledge Graph
The KG interface is almost entirely English-only in its helper text and settings.

- `src/components/kg/KGConceptMap.tsx:526` — "Drag to pan · scroll to zoom · double-click node to pin" — `kg.help`
- `src/components/kg/KGConceptMap.tsx:581` — "Graph view settings" — `kg.settings.title`
- `src/components/kg/KGConceptMap.tsx:586` — "Repel Force" — `kg.settings.repelForce`
- `src/components/kg/KGConceptMap.tsx:603` — "Link Distance" — `kg.settings.linkDistance`
- `src/components/kg/KGConceptMap.tsx:620` — "Center Gravity" — `kg.settings.centerGravity`
- `src/components/kg/KGConceptMap.tsx:637` — "Label Threshold" — `kg.settings.labelThreshold`
- `src/components/kg/KGConceptMap.tsx:660` — "Scale node size by connections" — `kg.settings.scaleByConnections`
- `src/components/kg/KGConceptMap.tsx:671` — "Color code by teacher" — `kg.settings.colorByTeacher`

## 3. Practices
While content is localized via `getLocalizedPractice`, many UI labels and meta-tags remain hardcoded.

- `src/pages/PracticeDetailPage.tsx:147` — "Copied!" — `common.copied`
- `src/pages/PracticeDetailPage.tsx:152` — "Share guide" — `practices.detail.share`
- `src/pages/PracticeDetailPage.tsx:188` — "Open in YouTube" — `practices.detail.openInYouTube`
- `src/pages/PracticeDetailPage.tsx:243` — "Why this practice" — `practices.detail.whyPractice`
- `src/pages/PracticeDetailPage.tsx:255` — "How to do it" — `practices.detail.howToDoIt`
- `src/pages/PracticeDetailPage.tsx:277` — "Key Benefits" — `practices.detail.keyBenefits`
- `src/pages/PracticesPage.tsx:145` — "Today's Wisdom" — `practices.dailyWisdom.title`
- `src/pages/PracticesPage.tsx:166` — "Wisdom of the Day" — `practices.dailyWisdom.badge`
- `src/pages/PracticesPage.tsx:175` — "— Sri Preethaji & Sri Krishnaji" — `common.gurusName`
- `src/pages/PracticesPage.tsx:188` — "Your favorites" — `practices.sections.favorites`
- `src/pages/PracticesPage.tsx:209` — "All practices" — `practices.sections.all`

## 4. Landing & Onboarding
Most landing text is translated, but demo prompts and aria-labels are missed.

- `src/components/landing/DemoModal.tsx:225` — "New here?" — `landing.demo.newHere`
- `src/components/landing/DemoModal.tsx:202` — "See how AskMukthiGuru works in a three-step tour" — `landing.demo.tourAria`
- `src/components/landing/DemoModal.tsx:117` — "Close tour" — `landing.demo.closeTourAria`

## Top 5 quick-win files
These files have the highest density of hardcoded strings (>5 each) and already import `useTranslation`.

1. `src/pages/ProfilePage.tsx` (>50 hits)
2. `src/components/profile/MemoryManager.tsx` (>5 hits)
3. `src/components/kg/KGConceptMap.tsx` (>8 hits)
4. `src/pages/PracticeDetailPage.tsx` (>6 hits)
5. `src/pages/PracticesPage.tsx` (>5 hits)
