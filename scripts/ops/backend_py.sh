#!/usr/bin/env bash
# Run Python inside the backend container from /app with PYTHONPATH=/app.
#   backend_py.sh script.py [args...]   script is read from the host, args land in sys.argv
#   backend_py.sh -c 'code' [args...]
#   echo 'code' | backend_py.sh -
# Sweeps: for x in a b c; do backend_py.sh sweep.py "$x"; done   (one script, read only the results)
# Exit code is the container's; nothing is piped through tail, so failures stay visible.
set -euo pipefail
export PATH="$HOME/.docker/bin:$PATH"
container="${BACKEND_CONTAINER:-mukthiguru-backend}"
run=(docker exec -w /app -e PYTHONPATH=/app)

[ $# -ge 1 ] || { echo "usage: backend_py.sh script.py [args...] | -c 'code' [args...] | -" >&2; exit 2; }

case "$1" in
  -c) shift; exec "${run[@]}" "$container" python3 -c "$@" ;;
  -)  exec "${run[@]}" -i "$container" python3 - ;;
  *)  script="$1"; shift
      [ -f "$script" ] || { echo "backend_py.sh: no such file: $script" >&2; exit 2; }
      exec "${run[@]}" -i "$container" python3 - "$@" < "$script" ;;
esac
