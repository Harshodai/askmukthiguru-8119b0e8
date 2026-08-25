#!/bin/sh
set -u
BASE='http://localhost:8000'
for query in 'What is the beautiful state?' 'What is the difference between stillness and the beautiful state?' 'नमस्ते गुरुजी, सुंदर अवस्था क्या है?' 'What is stillness?'; do
  session=$(curl -sS --max-time 15 -X POST "$BASE/api/auth/anon-session" -H 'Content-Type: application/json' -d '{}')
  token=$(printf '%s' "$session" | sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  if [ -z "$token" ]; then
    echo "QUERY=$query SESSION=FAILED"
    continue
  fi
  started=$(date +%s)
  result=$(curl -sS --max-time 45 -X POST "$BASE/api/chat" -H 'Content-Type: application/json' --data "{\"user_message\":\"$query\",\"session_id\":\"$token\",\"messages\":[]}")
  job=$(printf '%s' "$result" | sed -n 's/.*"job_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  if [ -z "$job" ]; then
    echo "QUERY=$query ADMISSION=$(printf '%s' "$result" | head -c 180)"
    continue
  fi
  status=''
  body=''
  i=0
  while [ "$i" -lt 40 ]; do
    i=$((i+1))
    sleep 1
    body=$(curl -sS --max-time 20 -H "X-Session-Id: $token" "$BASE/api/jobs/$job")
    status=$(printf '%s' "$body" | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    case "$status" in completed|failed|cancelled) break;; esac
  done
  ended=$(date +%s)
  elapsed=$((ended-started))
  sanitized=$(printf '%s' "$body" | sed -E 's/"(user_id|token|session_id)"[[:space:]]*:[[:space:]]*"[^"]*"/"\1":"<redacted>"/g' | head -c 5000)
  echo "QUERY=$query"
  echo "JOB=$job STATUS=$status ELAPSED_MS=$elapsed POLLS=$i"
  printf '%s\n' "$sanitized"
done
