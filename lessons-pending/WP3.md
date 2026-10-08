### L-HELPLINE-ORDER-1 (2026-10-07): 112 served before Tele-MANAS; KIRAN unflagged
Root cause: config/helplines.yaml and the in-code fallback listed 112 first, so the compact two-line block (first India entry) led with generic emergency instead of the call-verified national mental-health line. KIRAN (reportedly merging into Tele-MANAS) had no status field.
Rule: helplines are served in file order within a region; India leads with Tele-MANAS. Unconfirmed lines carry `status: needs_call_confirmation` and never a last_verified_by_call date. No crisis number in src/locales, src/components, src/pages (frontend mirrors src/lib/crisisHelplines.ts, drift-tested).
Test: backend/tests/test_helplines_india_ordering.py
