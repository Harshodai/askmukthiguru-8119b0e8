# Human gates

Agents prepare evidence packs at `docs/agent/gates/Gx-evidence.md`. **Only a named human marks a gate passed** (fill in "Signed by" and date). Agents never edit the sign-off lines.

| Gate | Name | Evidence required | Human owner | Blocks |
|---|---|---|---|---|
| G0 | Plan approved | Phase plan, risks, decisions needed | Project lead | Any implementation |
| G1 | Safety | 100% of high-risk multi-turn scenarios follow the crisis protocol in every pilot language; judge calibrated against clinician-labeled cases; independent risk monitor tested; helplines verified by a human placing test calls/texts (last_verified_by_call, not merely last_checked_public_listing); kill switch tested; clinician or senior faculty sign-off | Safety owner + clinician | Any user access |
| G2 | Rights | Register covers 100% of served sources with rights basis, holder and written approval; unregistered sources blocked at serve time; git history checked | Rights owner | Any user access |
| G3 | Privacy | Consent and notice in pilot languages; 18+ gate; deletion and export tested; retention configured; data map; LLM vendor review | Privacy owner | Any user access |
| G4 | Cost and performance | Monthly cap and kill switch tested; latency targets met under load test; cost per conversation known | Operations owner | Pilot start |
| G5 | Pilot start | G1 to G4 signed; named on-call contact; faculty handoff contact named; support text reviewed | Project lead | Pilot |
| G6 | Scale | Pilot results against agreed bars; incident review; Dasas decision recorded | Project lead + Dasas | Public rollout |

Sign-off template (per gate):
`Signed by: ______  Role: ______  Date: ______  Exceptions (owner, due date): ______`
