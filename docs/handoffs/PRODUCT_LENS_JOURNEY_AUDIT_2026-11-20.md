# Product lens: signed-out user journey audit (2026-11-20)

Method: walked the live local app as a new signed-out user in Chrome. Admin and signed-in
pages were NOT audited (login not completed in the audited browser). Scores are judgement, not data.
Status of open work stays in `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`; this is a note, not a plan.

## Goal check
Goal = a seeker gets the teacher's own verbatim words as a clip (invariants 1, 15, 21).
Time-to-value today: consent modal, landing, chat, then a reply. In the one distress-adjacent
question tested, the reply was a safety-routed conversational message, not a clip. That is
correct for safety, but it means the first win a new user sees is NOT the product promise.

## Journey (signed out)
| Step | Verdict |
|---|---|
| Consent modal | Clear, real tel: links. Fine. |
| Landing | Strong. Hero text was hard to read over the photo (fixed). Heading order skipped (fixed). |
| First question | Works end to end. Quota shown ("4 of 5 free questions left"). |
| Sidebar title | BUG, fixed: provider-outage apology saved as the title (root cause below). |
| My Reflections | Dumped to a generic login with no reason. Fixed: reason line shown; return path already worked. |
| Sign up | Heading said "Sign in"; OAuth hidden with no explanation. Fixed. |
| Public pages | Headings hidden under the fixed navbar on 11 pages. Fixed in PublicShell. |

## Root cause worth remembering
`OpenRouterService._graceful_degradation` returns a canned apology string on the standalone path
instead of raising. Any caller that treats `generate()` output as content will persist it.
`/api/chat/title` did. `text_quality_filter.find_artifact` already detects these strings.
Other `generate()` callers that store or display raw output should be checked the same way.

## Top 3 next (judgement, not measured)
1. Make the first answer show the product promise: measure what share of first questions get a
   clip vs a static abstain, then work on the gap.
2. Complete the admin and signed-in audit (My Reflections, Profile, Notebooks, admin tabs).
3. Hardcoded English strings (e.g. the meditation voice badge) bypass i18n in a multilingual product.

## Anti-goals
No new features until the first-answer clip rate is measured. No UI restyle.

## Not verified
Admin, signed-in flows, real-device mobile, screen reader, reduced motion.
