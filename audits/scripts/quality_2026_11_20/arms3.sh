#!/bin/zsh
# Interleaved arm runs across two images. Usage: arms3.sh OUTDIR "OFF@A:1 D3@B:1 ..." (A/B = tags backend-backend:imgA/imgB)
# Each run: recreate the backend with the arm's env (clears the in-process HyDE cache),
# wait healthy, record image id / tree diff hash / load, run the eval, record validity counters.
set -u
OUT=$1; ORDER=$2
REPO=/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
EVAL=$REPO/audits/work/2026-11-20-quality/eval_set_v2.json
HERE=$REPO/audits/scripts/quality_2026_11_20
export PATH="$HOME/.docker/bin:$PATH"
mkdir -p $OUT
override() {  # $1 arm -> override yml path (empty for OFF)
  local f=$OUT/arm_$1.yml
  case $1 in
    OFF) echo ""; return;;
    X) printf 'services:\n  backend:\n    environment:\n      FIRST_PERSON_RELEVANCE_EXACT_N_ENABLED: "true"\n' > $f;;
    R) printf 'services:\n  backend:\n    environment:\n      FIRST_PERSON_META_FOLLOWUP_ENABLED: "true"\n      FIRST_PERSON_CONTEXT_SEEN_RERANK_ENABLED: "true"\n      FIRST_PERSON_ANSWERABILITY_PREFETCH_ENABLED: "true"\n      FIRST_PERSON_MULTIPART_ENABLED: "true"\n' > $f;;
    ALL) printf 'services:\n  backend:\n    environment:\n      FIRST_PERSON_RELEVANCE_EXACT_N_ENABLED: "true"\n      FIRST_PERSON_META_FOLLOWUP_ENABLED: "true"\n      FIRST_PERSON_CONTEXT_SEEN_RERANK_ENABLED: "true"\n      FIRST_PERSON_ANSWERABILITY_PREFETCH_ENABLED: "true"\n      FIRST_PERSON_MULTIPART_ENABLED: "true"\n' > $f;;
    D3) printf 'services:\n  backend:\n    environment:\n      FIRST_PERSON_RELEVANCE_MIN_SCORE: "3"\n' > $f;;
    H3) printf 'services:\n  backend:\n    environment:\n      FIRST_PERSON_RELEVANCE_MIN_SCORE: "3"\n      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5\n' > $f;;
    H2) printf 'services:\n  backend:\n    environment:\n      FIRST_PERSON_RELEVANCE_MODEL: anthropic/claude-haiku-5.5\n' > $f;;
    *) echo "unknown arm $1" >&2; exit 2;;
  esac
  echo $f
}
for spec in ${=ORDER}; do
  armimg=${spec%%:*}; rep=${spec##*:}; arm=${armimg%%@*}; img=${armimg##*@}; tag=${arm}${img}_r${rep}
  docker tag backend-backend:img$img backend-backend:latest || exit 5
  ov=$(override $arm)
  cd $REPO/backend
  if [ -n "$ov" ]; then docker compose -p backend -f docker-compose.yml -f $ov up -d --no-deps --force-recreate backend > $OUT/$tag.recreate.log 2>&1
  else docker compose -p backend up -d --no-deps --force-recreate backend > $OUT/$tag.recreate.log 2>&1; fi
  for i in $(seq 1 60); do curl -s -m3 localhost:8000/api/healthz | grep -q alive && break; sleep 5; done
  sleep 20  # warm-up: models load lazily
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  { echo "start $start"; echo "load_start $(sysctl -n vm.loadavg)";
    echo "image $(docker inspect -f '{{.Image}}' mukthiguru-backend)";
    echo "diff_before $(cd $REPO && git diff | shasum | cut -c1-12)";
    echo "fresh $(cd $REPO && make -s verify-stack-fresh 2>&1 | tail -1)";
    echo "flags $(docker exec mukthiguru-backend sh -c 'env | grep -E "RELEVANCE_MIN|RELEVANCE_MODEL|EXACT_N|META_FOLLOWUP|SEEN_RERANK|PREFETCH|MULTIPART" | sort | tr "\n" " "')"; } > $OUT/$tag.meta
  python3 $HERE/run_eval.py $EVAL $OUT/$tag.jsonl --arm ${arm}${img} --rep $rep --conc 3 > $OUT/$tag.log 2>&1
  docker logs --since $start mukthiguru-backend > $OUT/$tag.backend.log 2>&1
  L=$OUT/$tag.backend.log
  { echo "end $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "load_end $(sysctl -n vm.loadavg)";
    echo "diff_after $(cd $REPO && git diff | shasum | cut -c1-12)";
    echo "scorer_timeouts $(grep -c 'Relevance check attempt .* failed (TimeoutError)' $L)";
    echo "scorer_indeterminate $(grep -c 'Relevance check indeterminate' $L)";
    echo "http_402 $(grep -c 'status=402\|402 Payment\|insufficient credits\|Insufficient credits' $L)";
    echo "budget_block $(grep -ci 'budget exceeded\|budget_guard' $L)";
    echo "turns $(wc -l < $OUT/$tag.jsonl)"; } >> $OUT/$tag.meta
done
cd $REPO/backend && docker tag backend-backend:imgB backend-backend:latest; docker compose -p backend up -d --no-deps --force-recreate backend > $OUT/restore.log 2>&1
echo done > $OUT/ALL_DONE
