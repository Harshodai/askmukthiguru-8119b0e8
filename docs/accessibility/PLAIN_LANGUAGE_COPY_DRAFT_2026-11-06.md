# Plain-language copy: DRAFT for owner review

Status: DRAFT. Nothing here is in the app. The owner decides each line (task NEW-A11Y-9, findings A11Y-17d and A11Y-17e).
Rule used: short sentences, one idea each, no terms a first-time seeker may not know.
Limits: do not edit helpline text or phone numbers. Teacher quotes stay verbatim and are not part of this list.

| # | Where | Today | Proposed | Why |
|---|---|---|---|---|
| 1 | Welcome message, `src/components/chat/ChatHelpers.tsx:65` | "If a recorded teaching matches, you will receive the teacher's verbatim words with a direct video clip." | "If a recorded teaching fits your question, you will see the teacher's own words and a video clip of them." | "verbatim" is not common speech. |
| 2 | Same message | "If no teaching addresses your question, the guide abstains honestly and offers a stillness practice." | "If no recorded teaching fits your question, we will say so. We may offer a short quiet practice instead." | "abstains" and "stillness practice" are unclear. |
| 3 | Same message | "In cases of acute emotional distress, professional crisis care lines are provided." | "If you are in deep distress, we will show phone lines where trained people can help." | Shorter, concrete. Do not change the lines themselves. |
| 4 | Badge, `src/lib/relatedLabel.ts` | "Related, not a direct answer" | Keep the badge text (it is pinned by tests and by the backend). Add one line under it: "This clip is on a nearby topic. Try asking again in other words." | The badge does not say what to do next. |
| 5 | "Get help now" dialog, `src/components/common/GetHelpNow.tsx` | "If you are in danger or thinking of harming yourself, call one of these lines now. Mukthi Guru is not a crisis service." | Owner and clinician to confirm the wording. | New copy in a safety surface. Needs the clinician reviewer, not only the owner. |
| 6 | Delete-account flow, `src/components/profile/CancelFlow.tsx` | "Permanently delete your account?" and "Data retention" | "Delete your account for good?" and "What should happen to your data?" | Plainer. The retention options themselves are decision D-19 and are not changed here. |

Not done, and why:
- No i18n files were edited. Each change needs a translation by a native-speaker reviewer (human gate in CLAUDE.md "Open work").
- No readability score was measured. UNPROVEN that the proposals read at a lower level.
