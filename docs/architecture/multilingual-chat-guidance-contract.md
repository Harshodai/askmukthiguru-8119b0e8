# Multilingual Teacher-Attributed Chat Contract

The chat landing experience makes the product’s role explicit before a seeker
starts a conversation. AskMukthiGuru provides guidance **inspired by and
attributed to the teachings of Sri Preethaji and Sri Krishnaji**. It does not
claim to be either teacher, does not fabricate a first-person quotation, and does
not replace emergency, medical, or mental-health support.

| Interaction element | Behaviour | Safety and quality boundary |
|---|---|---|
| Guidance context panel | Appears before the composer on a new conversation and names the teaching lineage | Uses “inspired by the teachings of” language rather than an impersonating identity claim |
| Current guidance path | Shows the selected assistant name when a scoped assistant has been chosen | The frontend selection remains only a request hint; server-side assistant scope remains authoritative |
| Priority language controls | English, Hinglish, Hindi, Telugu, Tamil, and Kannada are directly selectable | The complete selector remains available for the broader supported language set |
| Hinglish | Uses canonical `hinglish` for the chat request | The frontend preserves code-mixed input rather than translating it into English; backend language routing remains responsible for model handling |
| Evidence and safety | Existing evidence-support labels and crisis routing continue unchanged | Language and teacher context must not turn support labels into claims of certainty or bypass crisis pre-emption |

## Implementation Rules

The guidance panel is a **landing-state affordance**, not a new prompt source. It
must not append hidden instructions, teacher names, or user language selections
to the message text. Language controls call the existing profile and request
language flow; the backend must continue to resolve corpus scope from its own
assistant registry.

The panel’s emergency line is intentionally concise. The deterministic severe
and crisis workflow remains the authoritative safety path and must be available
in the selected language through the existing response pipeline.

## Validation

The redesign requires focused component and translation regressions, the complete
frontend suite, and the production Vite build. Accessibility assertions must
cover labelled language controls, selected-state semantics, keyboard reachability,
and visible attribution language.
