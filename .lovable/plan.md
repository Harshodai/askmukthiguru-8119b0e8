# Ruthless UI/UX Audit — AskMukthiGuru

**Method:** Playwright captures at 384 / 820 / 1440 across `/`, `/chat`, `/auth`, `/practices`, `/profile`. Console + visual diff. Skills applied: `token-optimization`, `accessibility`, `chat-ui-composition`, `design-craft`, `redesign`.

**Confidence the current UI is "top notch": 5.5 / 10.**
Foundation (Golden Hour palette, typewriter display, lotus hero) is distinctive and on-brand. Execution has a stack of visible bugs and craft misses that any first-time visitor will notice. Not excellent yet — fixable in one focused pass.

---

## Critical (must fix — visibly broken)

1. **Scroll-reveal animations stuck at low opacity.** On desktop scroll, practice cards stair-step from 100% → ~15% opacity (Soul Sync visible, Daily Reflection almost invisible). Section titles ("The Serene Mind Meditation", "Founders of Ekam") render permanently faded. Root cause: IntersectionObserver / framer `whileInView` not firing for elements that mount already in viewport after scroll. Fix: switch to `viewport={{ once: true, amount: 0.1 }}` + `initial={false}` for above-fold, or replace with `animate` driven by mount.
2. **Sticky navbar overlaps content on every section break.** Mobile scroll1/2/3/5 all show heading text bleeding under the floating nav pill ("Sri Preethaji & Sri Krishnaji" name + "Founders of Ekam" tag hidden behind it). Need `scroll-margin-top` on section anchors and an extra `pt-[nav-height]` on first child of each `<section>`.
3. **Hero badge collision on mobile.** "Guided by Ancient Wisdom, Powered by AI" pill sits directly behind the navbar at viewport top. Add top padding to hero or lower badge.
4. **Cookie banner blocks primary CTA on first paint.** On 384px the banner covers the "Begin Your Journey" button and on `/auth` it covers the password field. Move to bottom-left mini toast, or auto-collapse after 4s, or render only after first scroll.
5. **Guru card body copy at ~30% opacity on desktop.** "Founders of Ekam & The Oneness Movement", tags ("Beautiful State", "Consciousness"…), and the entire bio paragraph render washed out — same stuck-animation root cause but worth calling out: chips should never be sub-AA contrast.

## High (craft / consistency)

6. **Monospace everywhere kills readability.** Typewriter is great for the H1 and section labels; using it for 300-char body paragraphs (quote block, "When stress overwhelms you…") drops scan speed sharply. Lock monospace to display + eyebrow only; switch body to the paired sans (already loaded).
7. **Header avatar contrast.** "SE" initials sit on a pale gold disc on a pale gold header — fails 3:1. Darken disc or invert initials.
8. **CTA disclaimer contrast.** "This is an AI companion trained on spiritual teachings…" sits at ~`muted-foreground/50` over the hero image — fails AA. Bump to `muted-foreground` solid + subtle backdrop blur.
9. **Mobile menu has no visible focus state and the trigger has no `aria-label`** (hamburger icon-only button).
10. **Tablet (820) wastes horizontal space.** Hero and Meet-the-Gurus stay in a narrow column with `max-w-2xl` while the page is 820 wide → big empty rails. Use `max-w-3xl` at `md`, `max-w-5xl` at `lg`.
11. **Lotus hero image is decorative but has no `alt=""`** declared — fix for a11y noise.
12. **Section dividers (`<hr>` / gradient bands) appear twice in a row** between "How It Works" and "Daily practices" creating a 200px empty white gap on mobile (scroll5 evidence). Collapse.

## Medium

13. **Console noise:** React Router v7 future-flag warnings on every nav; `[Google One Tap] VITE_GOOGLE_CLIENT_ID not configured` warning fires for anonymous users. Silence (opt-in to v7 flags; gate One Tap behind env check).
14. **Practice card stars (favorite toggle)** have no tooltip, no `aria-pressed`, no toast confirmation.
15. **"Start Chat" desktop CTA and "Begin Your Journey" hero CTA say different things for the same action** — pick one verb and reuse.
16. **No skeletons** while landing sections lazy-mount; the page paints empty bands first.
17. **Footer not visible** on any capture — either missing or pushed below an `h-screen` section using `h-screen` instead of `h-dvh`.

## Chat surface (from `/chat` redirect → `/auth`)

Cannot audit authenticated chat without a session in this run. Per the existing `.lovable/plan.md` audit list (items 1–12), known gaps remain: assistant bubble max-width drift, composer jitter, sample-pill mobile overflow, missing AI-Elements migration. These remain valid and should be folded into the same sprint.

## Quick wins (≤ 1 hour each)

- Fix stuck `whileInView` (one change in `motion.ts` preset propagates everywhere).
- Add `scroll-margin-top: 80px` to `section[id]`.
- Swap body font from monospace to paired sans inside `.prose` and `<p>` outside hero.
- Darken avatar disc, fix disclaimer contrast, add hamburger `aria-label`.
- Auto-dismiss cookie banner on first scroll OR move to bottom-corner toast.

## Execution plan (one sprint)

```text
P1 (today)         Animation/opacity fix · navbar overlap · cookie banner placement · avatar+disclaimer contrast · hamburger a11y
P2 (next)          Typography split (display vs body) · tablet width scale · footer/dvh fix · React Router v7 flags
P3 (chat sprint)   Carry out .lovable/plan.md Part A (1–12) + AI Elements migration of chat surface
P4 (polish)        Skeletons, focus rings, motion preset consolidation, alt text sweep, Lighthouse + axe pass
```

## Target after fixes

- Confidence: **9 / 10** (10/10 reserved for post-chat AI-Elements migration + a11y axe-clean).
- WCAG AA across all surfaces, no stuck animations, no overlap, single typography system, navbar respects safe areas, cookie banner non-blocking.

---

**Approve to proceed** and I'll start P1 immediately (estimated ~30 min, single commit, screenshots before/after).
