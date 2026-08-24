#!/usr/bin/env bash
set -u
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
OUT="${RERUN_EVIDENCE_DIR:-$ROOT/docs/production-readiness/rerun-2026-08-24}"
mkdir -p "$OUT"

run_track() {
  local name="$1"; shift
  {
    echo "=== TRACK: $name ==="
    echo "UTC: $(date -u +%FT%TZ)"
    echo "HEAD: $(git -C "$ROOT" rev-parse HEAD)"
    "$@"
  } > "$OUT/$name.txt" 2>&1
}

common_files() {
  find . -path './node_modules' -prune -o -path './backend/.venv' -prune -o -path './.git' -prune -o -type f -print | sort
}

(
run_track product bash -lc 'rg -n "Start Chat|Meditation|Second Brain|Knowledge Graph|memory|attachment|audio|push|admin" src/pages src/components README.md docs --glob "!**/node_modules/**" | head -n 600'
) &
(
run_track frontend bash -lc 'find src -type f \( -name "*.tsx" -o -name "*.ts" -o -name "*.css" \) | sort; echo "--- hook warnings ---"; npm run lint 2>&1 | rg -n "warning|error|react-hooks|color-contrast" | head -n 300'
) &
(
run_track backend bash -lc 'find backend/app backend/services backend/rag -type f -name "*.py" | sort; echo "--- TODO/FIXME/HACK ---"; rg -n "TODO|FIXME|HACK|except Exception|pass$|NotImplemented|mock|fallback" backend/app backend/services backend/rag --glob "*.py" | head -n 800'
) &
(
run_track rag bash -lc 'rg -n "class .*Stage|Pipeline|retriev|rerank|CRAG|CoVe|Self.?RAG|faithful|grounding|citation|verification|Qdrant|embedding" backend/app backend/rag backend/services scripts/eval tests --glob "*.py" --glob "*.ts" | head -n 1200'
) &
(
run_track knowledge_graph bash -lc 'rg -n "Neo4j|neo4j|LightRAG|lightrag|graph|entity|relationship|travers" backend scripts src tests --glob "*.py" --glob "*.ts" --glob "*.tsx" | head -n 1200'
) &
(
run_track ai_evaluation bash -lc 'find scripts/eval tests backend/tests -type f | sort | rg "eval|rag|faith|quality|citation|ndcg|mrr|benchmark|gold|advers|refus|halluc" | head -n 500; rg -n "RAGAS|faithfulness|answer_relevancy|context_precision|NDCG|Recall@|MRR|golden|held.?out|benchmark" scripts tests backend --glob "*.py" --glob "*.md" | head -n 1000'
) &
(
run_track memory bash -lc 'rg -n "Second Brain|second_brain|memory|forget|delete|retention|TTL|user_id|vault|reflection" backend src supabase scripts tests --glob "*.py" --glob "*.ts" --glob "*.tsx" --glob "*.sql" | head -n 1400'
) &
(
run_track security bash -lc 'find .github scripts/security backend/tests tests/e2e supabase -type f 2>/dev/null | sort; echo "--- security patterns ---"; rg -n "RLS|AAL2|MFA|service_role|jwt|secret|password|upload|attachment|prompt injection|CORS|CSRF|rate.limit|redirect|allowlist|gitleaks|bandit" .github scripts backend src supabase tests --glob "*.py" --glob "*.ts" --glob "*.tsx" --glob "*.sql" --glob "*.yml" --glob "*.yaml" | head -n 1600'
) &
(
run_track database bash -lc 'find supabase -type f -maxdepth 5 2>/dev/null | sort; rg -n "CREATE TABLE|CREATE INDEX|CREATE POLICY|WITH CHECK|ENABLE ROW LEVEL SECURITY|DELETE|UPDATE|ON CONFLICT|transaction|pool|index" supabase backend --glob "*.sql" --glob "*.py" | head -n 1400'
) &
(
run_track infrastructure bash -lc 'find . -maxdepth 4 -type f \( -name "Dockerfile*" -o -name "docker-compose*.yml" -o -name "*.yaml" -o -name "*.yml" -o -name "railway*" -o -name "Procfile" \) -not -path "./node_modules/*" -not -path "./backend/.venv/*" | sort; echo "--- health/startup ---"; rg -n "health|readiness|startup|graceful|worker|celery|uvicorn|gunicorn|FORWARDED_ALLOW_IPS|profile|resource|replica|rollback" backend Dockerfile* docker-compose* infrastructure k8s .github --glob "*.py" --glob "*.yml" --glob "*.yaml" --glob "Dockerfile*" | head -n 1400'
) &
(
run_track observability bash -lc 'rg -n "metric|counter|histogram|trace|span|opentelemetry|Sentry|logger|request_id|trace_id|latency|token|cost|alert|SLO|dashboard" backend src scripts docs .github --glob "*.py" --glob "*.ts" --glob "*.tsx" --glob "*.md" --glob "*.yml" | head -n 1400'
) &
(
run_track mobile bash -lc 'find android ios -maxdepth 4 -type f 2>/dev/null | sort | head -n 500; cat capacitor.config.ts; echo "--- native references ---"; rg -n "Capacitor|push|deep.?link|oauth|keyboard|speech|permission|backButton|App.addListener|network" src android ios --glob "*.ts" --glob "*.tsx" --glob "*.swift" --glob "*.kt" --glob "*.xml" | head -n 1200'
) &
(
run_track testing bash -lc 'find tests backend/tests src/test src/tests .github -type f 2>/dev/null | sort | wc -l; find tests backend/tests src/test src/tests -type f 2>/dev/null | sort | head -n 1200; echo "--- test skips/todos ---"; rg -n "skip|TODO|xfail|only\(|describe\.only|test\.only|flaky|mock|stub" tests backend/tests src/test src/tests --glob "*.py" --glob "*.ts" --glob "*.tsx" | head -n 1200'
) &
(
run_track cost_performance bash -lc 'rg -n "cache|TTL|coalesc|semaphore|timeout|retry|backoff|rate.limit|token|cost|model|provider|embedding|rerank|queue|concurr|batch|latency" backend src scripts docs --glob "*.py" --glob "*.ts" --glob "*.tsx" --glob "*.md" | head -n 1600'
) &
(
run_track docs_agent_ready bash -lc 'find . -maxdepth 4 -type f \( -name "AGENTS.md" -o -name "lessons.md" -o -path "./.claude/*" -o -path "./.codex/*" -o -path "./.agents/*" -o -path "./.opencode/*" \) -not -path "./node_modules/*" -not -path "./backend/.venv/*" | sort; echo "--- instruction counts ---"; find .claude/tasks -type f 2>/dev/null | wc -l; echo "--- conflicting/stale claims ---"; rg -n "production.ready|production ready|complete|active|89,053|8,750|TODO|remaining|not ready|paused|absent" AGENTS.md lessons.md docs README.md .claude .codex .opencode --glob "*.md" --glob "*.toml" | head -n 1400'
) &
(
run_track red_team bash -lc 'rg -n "except Exception|pass$|fallback|default|demo|mock|sample|localhost|127\.0\.0\.1|0\.0\.0\.0|allow_origins|service_role|admin|test.?auth|benchmark|TODO|FIXME|HACK" backend src scripts supabase .github --glob "*.py" --glob "*.ts" --glob "*.tsx" --glob "*.sql" --glob "*.yml" --glob "*.yaml" | head -n 1800'
) &
wait
printf "Completed parallel tracks in %s\n" "$OUT"
