# Ask Mukthi Guru Expo Companion

This is the separate Expo SDK 54 companion client. It uses the existing backend as the only source of chat, capabilities, safety, evidence, and privacy policy; it does not contain a second backend or a local answer engine.

Set `EXPO_PUBLIC_API_URL` to the backend base URL, then run `npm install`, `npm run typecheck`, and `npx expo start`. The local-only storage boundary is limited to response-form preferences and an incognito flag. Credentials, authenticated session handling, streaming parity, native permissions, device screenshots, and EAS signing remain release-gated work.
