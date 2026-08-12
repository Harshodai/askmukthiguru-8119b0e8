# AskMukthiGuru Product Demo Video Handoff

**Status:** The landing-page integration is ready. Add the approved, captioned MP4 URL as `VITE_LANDING_DEMO_VIDEO_URL` at build time. Until a final video is supplied, the existing accessible three-step interactive tour remains the main landing-page demo action.

## Objective

This is a **product demonstration**, not a teacher simulation or a claim of direct speech. It shows the value sequence a new seeker should understand in under 70 seconds: ask naturally, receive a source-aware response, inspect the sources and response confidence, and personalise the experience. The visual treatment should be calm and premium, but it must show real product behavior rather than abstract spirituality.

## Storyboard and narration

| Time | Product moment | On-screen treatment | Narration / supers |
|---|---|---|---|
| 0–05 s | Landing hero | Slow reveal of the existing hero and “See how this works” action. | **A calmer way to explore a question.** |
| 05–14 s | Natural-language question | Cursor enters: “I feel restless before sleep. What can I do now?” | *Ask in your own words. No perfect phrasing is needed.* |
| 14–28 s | Grounded answer arrives | Show a concise response: lived difficulty → teaching → one optional practice. Keep citation markers visible. | *Receive guidance shaped around one clear next step—not a wall of generic advice.* |
| 28–39 s | Trust and provenance | Reveal the response-context card, source count, verifier confidence, then open the source panel. | *See when source links are available, inspect them, and keep a clear boundary between a teaching and a reflection.* |
| 39–50 s | Profile personalisation | Show Guidance Depth and Guru’s Tone settings updating the guidance preview. | *Choose how much explanation you want. The product explains its preferences before you save them.* |
| 50–61 s | Calm practice | Transition to the Serene Mind entry point and its short-duration option. | *When you need a pause, begin with a short, gentle practice.* |
| 61–70 s | Return to the hero CTA | “Start a conversation” and “See how this works” remain visible. | **Ask. Reflect. Return when you need steadiness.** |

## Production direction

Use a 16:9 master at 1920×1080, 24 or 30 fps, with a 9:16 cutdown prepared separately. Use authentic application screen capture on a clean seeded account; do not fake source counts, verifier scores, testimonials, or results. Keep any personal data, identifiers, and real user conversations out of the recording. Use motion to guide attention—gentle cursor movement, 250–400 ms UI emphasis, and no rapid cuts.

Narration should be warm Indian-English in cultural reference but globally clear. It should not imitate, impersonate, or suggest that either founder is speaking. The soundtrack should remain unobtrusive and should never sit under critical spoken safety information. Provide an edited transcript and timed WebVTT captions before publishing.

## Required final deliverables

| Asset | Requirement |
|---|---|
| `askmukthiguru-product-demo.mp4` | H.264 MP4, optimized for web, no autoplay audio. |
| `askmukthiguru-product-demo.vtt` | Caption file matching final narration and all meaningful onscreen claims. |
| `askmukthiguru-product-demo-poster.webp` | 16:9 poster with no embedded tiny text. |
| Transcript | Plain-text script for review, captions, and accessibility. |
| Cutdowns | 9:16 and 1:1 versions for product distribution, with revised safe areas. |

## Landing-page deployment

The main hero’s existing **“See how this works”** action now opens the three-step interactive tour and, when configured, the completed video at the top of that same dialog. This preserves a useful user experience if the video cannot load and avoids an autoplay or external-embed privacy cost.

Set the final build variable in the deployment environment:

```bash
VITE_LANDING_DEMO_VIDEO_URL=https://cdn.example.com/askmukthiguru-product-demo.mp4
```

Before release, verify keyboard access to the dialog, visible controls, caption availability, reduced-motion behavior, mobile layout, MP4 cache headers, poster loading, and the fallback tour with the variable intentionally absent.

## Available instrumental score

The approved full-demo underscore is available at `/media/askmukthiguru-product-demo-instrumental.mp3`. It is a **65.99-second**, stereo MP3 at **44.1 kHz / 192 kbps**, designed to remain under narration and to resolve after the final product-demo scene. Its SHA-256 is `640237abe3786e397fd91069593b7d261b1e7d0fc9f1c1f81e9560ea07b10af2`.

Use the score only as a separate, low-level narration bed in the final video edit; do not autoplay it on the landing page. During final assembly, duck it beneath spoken safety or source-attribution content and retain the accessible, muted-by-default landing-page demo behavior.
