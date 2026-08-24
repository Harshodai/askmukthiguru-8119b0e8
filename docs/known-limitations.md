# Known Limitations

This is an evidence record, not a production certification. Local tests use fixtures/mocks and do not prove deployed network policy, provider behavior, RLS, worker durability, restore, or browser journeys. Retrieval cases skip when live source identifiers do not match golden labels. Local readiness is false because `okf_compiled` is missing. The E2E run stalled and was stopped.

npm audit and Bandit are scoped scans; the gitleaks result covered approximately zero commits/bytes. No production, Railway, user account, corpus, Neo4j schema, or secret state was changed. The checkout is behind its remote and includes pre-existing user audit artifacts and a user-modified baseline that were preserved.
