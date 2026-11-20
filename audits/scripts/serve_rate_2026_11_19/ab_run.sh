#!/bin/zsh
# Paired A/B on the current tree. Usage: ab_run.sh <label> [override.yml]
set -u
S=/private/tmp/claude-501/-Users-harshodaikolluru-Public-askmukthiguru-8119b0e8/04bf9baa-635c-4a0c-a5f1-02540f80f62e/scratchpad
export PATH="$HOME/.docker/bin:$PATH"
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
docker compose -p backend build backend > $S/build_$1.log 2>&1 || exit 3
if [ -n "${2:-}" ]; then docker compose -p backend -f docker-compose.yml -f $2 up -d --no-deps --force-recreate backend >> $S/build_$1.log 2>&1
else docker compose -p backend up -d --no-deps --force-recreate backend >> $S/build_$1.log 2>&1; fi
for i in $(seq 1 60); do curl -s -m3 localhost:8000/api/healthz | grep -q alive && break; sleep 5; done
(cd .. && make verify-stack-fresh) > $S/fresh_$1.txt 2>&1 || exit 4
git diff -- . | shasum | cut -c1-12 > $S/diffhash_$1.txt
docker exec mukthiguru-backend sh -c 'env | grep -E "META_FOLLOWUP|EXACT_N|SEEN_RERANK|PREFETCH|MULTIPART|SERVER_SEEN" | sort' > $S/flags_$1.txt
cd $S && export BATTERY_BASE=http://localhost:8000 BATTERY_COLD=1
python3 tools/battery2.py ab_$1_2.jsonl > ab_$1_2.log 2>&1
python3 tools/battery.py ab_$1_1.jsonl > ab_$1_1.log 2>&1
docker logs mukthiguru-backend > $S/backend_$1.log 2>&1
