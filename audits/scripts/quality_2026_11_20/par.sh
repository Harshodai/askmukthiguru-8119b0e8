#!/bin/zsh
# Two arms SIMULTANEOUSLY on two backends (:8000 service `backend`, :8001 service `backend_b`).
# Usage: par.sh OUTDIR "PORT TAG ARM IMG EVAL" ["PORT TAG ARM IMG EVAL"]
#   ARM: OFF | X | H3 | D3 ; IMG: A | B (tags backend-backend:imgA / imgB) ; EVAL: path to eval json
set -u
OUT=$1; shift
REPO=/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
HERE=$REPO/audits/scripts/quality_2026_11_20
export PATH="$HOME/.docker/bin:$PATH"
mkdir -p $OUT
envyml() {  # $1 svc $2 arm $3 img -> override file
  local f=$OUT/ov_$1.yml
  {
    echo "services:"; echo "  $1:"
    if [ $1 = backend_b ]; then
      echo "    extends: {file: docker-compose.yml, service: backend}"
      echo "    container_name: mukthiguru-backend-b"
      echo "    ports: !override [\"8001:8000\"]"
    fi
    echo "    image: backend-backend:img$3"
    echo "    pull_policy: never"
    echo "    environment:"
    case $2 in
      OFF) echo "      EVAL_ARM: \"OFF\"";;
      X) echo "      FIRST_PERSON_RELEVANCE_EXACT_N_ENABLED: \"true\"";;
      H3) echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"3\""; echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5";;
      D3) echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"3\"";;
      H2) echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5";;
      P12) echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"3\""; echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5"; echo "      FIRST_PERSON_CONTEXT_USE_SPARSE: \"false\""; echo "      DISTRESS_LLM_ESCALATION_ENABLED: \"true\"";;
      PROD) echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5"; echo "      FIRST_PERSON_CONTEXT_USE_SPARSE: \"false\""; echo "      FIRST_PERSON_CONTEXT_CANDIDATE_LIMIT: \"10\""; echo "      FIRST_PERSON_CONTEXT_MAX_SPANS: \"5\""; echo "      FIRST_PERSON_SERVE_UNREGISTERED: \"false\""; echo "      FIRST_PERSON_LOCAL_REVIEW_ENABLED: \"false\""; echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"2\"";;
      PROD3) echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5"; echo "      FIRST_PERSON_CONTEXT_USE_SPARSE: \"false\""; echo "      FIRST_PERSON_CONTEXT_CANDIDATE_LIMIT: \"10\""; echo "      FIRST_PERSON_CONTEXT_MAX_SPANS: \"5\""; echo "      FIRST_PERSON_SERVE_UNREGISTERED: \"false\""; echo "      FIRST_PERSON_LOCAL_REVIEW_ENABLED: \"false\""; echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"3\"";;
      PRODR) echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5"; echo "      FIRST_PERSON_CONTEXT_USE_SPARSE: \"false\""; echo "      FIRST_PERSON_CONTEXT_CANDIDATE_LIMIT: \"10\""; echo "      FIRST_PERSON_CONTEXT_MAX_SPANS: \"5\""; echo "      FIRST_PERSON_SERVE_UNREGISTERED: \"false\""; echo "      FIRST_PERSON_LOCAL_REVIEW_ENABLED: \"false\""; echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"2\""; echo "      FIRST_PERSON_META_FOLLOWUP_ENABLED: \"true\""; echo "      FIRST_PERSON_CONTEXT_SEEN_RERANK_ENABLED: \"true\""; echo "      FIRST_PERSON_ANSWERABILITY_PREFETCH_ENABLED: \"true\""; echo "      FIRST_PERSON_MULTIPART_ENABLED: \"true\"";;
      PRODX) echo "      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5"; echo "      FIRST_PERSON_CONTEXT_USE_SPARSE: \"false\""; echo "      FIRST_PERSON_CONTEXT_CANDIDATE_LIMIT: \"10\""; echo "      FIRST_PERSON_CONTEXT_MAX_SPANS: \"5\""; echo "      FIRST_PERSON_SERVE_UNREGISTERED: \"false\""; echo "      FIRST_PERSON_LOCAL_REVIEW_ENABLED: \"false\""; echo "      FIRST_PERSON_RELEVANCE_MIN_SCORE: \"2\""; echo "      FIRST_PERSON_RELEVANCE_EXACT_N_ENABLED: \"true\"";;
      *) echo "bad arm $2" >&2; exit 2;;
    esac
  } > $f
  echo $f
}
one() {  # $1 svc $2 port $3 tag $4 arm $5 img $6 eval
  local svc=$1 port=$2 tag=$3 arm=$4 img=$5 ev=$6 cname
  cname=$([ $svc = backend ] && echo mukthiguru-backend || echo mukthiguru-backend-b)
  local ov=$(envyml $svc $arm $img)
  (cd $REPO/backend && docker compose -p backend -f docker-compose.yml -f $ov up -d --no-deps --force-recreate $svc) > $OUT/$tag.recreate.log 2>&1
  for i in $(seq 1 60); do curl -s -m3 localhost:$port/api/healthz | grep -q alive && break; sleep 5; done
  sleep 20
  local start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  { echo "start $start"; echo "port $port"; echo "load_start $(sysctl -n vm.loadavg)";
    echo "image $(docker inspect -f '{{.Image}}' $cname)";
    echo "flags $(docker exec $cname sh -c 'env | grep -E "CONTEXT_USE_SPARSE|CANDIDATE_LIMIT|MAX_SPANS|SERVE_UNREGISTERED|RELEVANCE_MIN|RELEVANCE_MODEL|EXACT_N|META_FOLLOWUP|SEEN_RERANK|PREFETCH|MULTIPART" | sort | tr "\n" " "')"; } > $OUT/$tag.meta
  MINT_CONTAINER=$cname BATTERY_BASE=http://localhost:$port python3 $HERE/run_eval.py $ev $OUT/$tag.jsonl --arm ${arm}${img} --rep ${tag##*_r} --conc ${CONC:-3} > $OUT/$tag.log 2>&1
  docker logs --since $start $cname > $OUT/$tag.backend.log 2>&1
  local L=$OUT/$tag.backend.log
  { echo "end $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "load_end $(sysctl -n vm.loadavg)";
    echo "scorer_timeouts $(grep -c 'Relevance check attempt .* failed (TimeoutError)' $L)";
    echo "scorer_indeterminate $(grep -c 'Relevance check indeterminate' $L)";
    echo "http_402 $(grep -c 'status=402\|402 Payment\|nsufficient credits' $L)";
    echo "http_429 $(grep -c 'status=429\|429 Too Many' $L)";
    echo "budget_block $(grep -ci 'budget exceeded\|budget_guard' $L)";
    echo "turns $(wc -l < $OUT/$tag.jsonl)"; } >> $OUT/$tag.meta
}
# Spec "PORT TAG ARM IMG EVAL" per argument (PORT 8000 -> service backend, 8001 -> backend_b).
for spec in "$@"; do
  set -- ${=spec}
  ([ $1 = 8000 ] && one backend 8000 $2 $3 $4 $5 || one backend_b 8001 $2 $3 $4 $5) &
done
wait
