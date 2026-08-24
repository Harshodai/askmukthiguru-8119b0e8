# Deployment Assessment

No deployment, Railway mutation, secret change, push, or external data action was performed. Promotion must build from a clean checkout, provision `okf_compiled` and all critical runtime artifacts, load secrets through the deployment manager, run reversible migrations, verify readiness, and execute the release matrix.

HTTP 200 is not sufficient: `/api/health` must report `ready=true` with every critical dependency healthy. Promotion also requires strict retrieval evaluation, live disposable integration tests, browser/mobile journey completion, backup/restore evidence, observability alert checks, and rollback compatibility. Railway checks remain read-only until separately authorized.
