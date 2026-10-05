#!/usr/bin/env bash
# ponytail: robust background runner for AskMukthiGuru audio archive downloads
# Supports single worker and distributed partition workers with rate-limiting and PID tracking.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${REPO_ROOT}/backend/.venv/bin/python3"
SCRIPT="${REPO_ROOT}/scripts/ops/audio_archive.py"

COMMAND="${1:-status}"
WORKER_ID="${2:-${WORKER_ID:-0}}"
NUM_WORKERS="${3:-${NUM_WORKERS:-1}}"
SLEEP_REQUESTS="${SLEEP_REQUESTS:-2.0}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-3.0}"
MAX_SLEEP_INTERVAL="${MAX_SLEEP_INTERVAL:-6.0}"

get_pid_file() {
    local wid="$1"
    local nworkers="$2"
    if [ "$nworkers" -gt 1 ]; then
        echo "/tmp/audio_archive_download_w${wid}.pid"
    else
        echo "/tmp/audio_archive_download.pid"
    fi
}

get_log_file() {
    local wid="$1"
    local nworkers="$2"
    if [ "$nworkers" -gt 1 ]; then
        echo "/tmp/audio_archive_download_w${wid}.log"
    else
        echo "/tmp/audio_archive_download.log"
    fi
}

start_single_worker() {
    local wid="$1"
    local nworkers="$2"
    local pid_file
    local log_file
    pid_file="$(get_pid_file "$wid" "$nworkers")"
    log_file="$(get_log_file "$wid" "$nworkers")"

    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file" || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "Worker ${wid}/${nworkers} is ALREADY running (PID: $pid). Log: $log_file"
            return 0
        fi
        rm -f "$pid_file"
    fi

    echo "Starting Audio Archive Downloader Worker ${wid} of ${nworkers}..."
    echo "  Rate limits:    requests=${SLEEP_REQUESTS}s, interval=${SLEEP_INTERVAL}-${MAX_SLEEP_INTERVAL}s"
    echo "  Log output:     ${log_file}"

    nohup "$PYTHON_BIN" -u "$SCRIPT" download \
        --worker-id "$wid" \
        --num-workers "$nworkers" \
        --sleep-requests "$SLEEP_REQUESTS" \
        --sleep-interval "$SLEEP_INTERVAL" \
        --max-sleep-interval "$MAX_SLEEP_INTERVAL" \
        --continuous \
        >> "$log_file" 2>&1 &

    local new_pid=$!
    echo "$new_pid" > "$pid_file"
    echo "Worker ${wid}/${nworkers} started successfully (PID: $new_pid)."
}

status_single_worker() {
    local wid="$1"
    local nworkers="$2"
    local pid_file
    local log_file
    pid_file="$(get_pid_file "$wid" "$nworkers")"
    log_file="$(get_log_file "$wid" "$nworkers")"

    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file" || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "Worker ${wid}/${nworkers} STATUS: RUNNING (PID: $pid)"
            echo "--- Recent Log Output (${log_file}) ---"
            tail -n 8 "$log_file" 2>/dev/null || true
            return 0
        else
            echo "Worker ${wid}/${nworkers} STATUS: STOPPED (stale PID file found)"
            rm -f "$pid_file"
            return 1
        fi
    else
        echo "Worker ${wid}/${nworkers} STATUS: NOT RUNNING"
        return 1
    fi
}

stop_single_worker() {
    local wid="$1"
    local nworkers="$2"
    local pid_file
    pid_file="$(get_pid_file "$wid" "$nworkers")"

    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file" || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "Stopping worker ${wid}/${nworkers} (PID: $pid)..."
            kill "$pid" || true
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" || true
            fi
            echo "Worker ${wid} stopped."
        else
            echo "Worker ${wid} process $pid was not running."
        fi
        rm -f "$pid_file"
    else
        echo "No PID file found for worker ${wid}/${nworkers}."
    fi
}

stop_all_workers() {
    echo "Stopping all active audio download workers..."
    # 1. Stop default single worker
    stop_single_worker 0 1 || true

    # 2. Stop any indexed workers (w0..w15)
    for w in $(seq 0 15); do
        local pf="/tmp/audio_archive_download_w${w}.pid"
        if [ -f "$pf" ]; then
            local p
            p="$(cat "$pf" || true)"
            if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
                echo "Stopping worker $w (PID: $p)..."
                kill "$p" || true
                sleep 0.5
                if kill -0 "$p" 2>/dev/null; then
                    kill -9 "$p" || true
                fi
            fi
            rm -f "$pf"
        fi
    done
    echo "All download workers stopped."
}

start_cluster() {
    local n="${2:-2}"
    echo "Starting cluster of $n distributed workers..."
    stop_all_workers
    sleep 1

    for ((i=0; i<n; i++)); do
        start_single_worker "$i" "$n"
        sleep 1
    done
    echo "Cluster of $n workers started successfully!"
}

status_all_workers() {
    echo "=== Audio Archive Download Workers Status ==="
    # Check default single worker
    if [ -f "/tmp/audio_archive_download.pid" ]; then
        status_single_worker 0 1 || true
        echo "---------------------------------------------"
    fi

    local found_any=0
    for w in $(seq 0 15); do
        local pf="/tmp/audio_archive_download_w${w}.pid"
        local lf="/tmp/audio_archive_download_w${w}.log"
        if [ -f "$pf" ]; then
            found_any=1
            local pid
            pid="$(cat "$pf" || true)"
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                echo "Worker $w STATUS: RUNNING (PID: $pid)"
                echo "--- Recent Log Output (${lf}) ---"
                tail -n 8 "$lf" 2>/dev/null || true
            else
                echo "Worker $w STATUS: STOPPED (stale PID file found)"
                rm -f "$pf"
            fi
            echo "---------------------------------------------"
        fi
    done

    if [ "$found_any" -eq 0 ] && [ ! -f "/tmp/audio_archive_download.pid" ]; then
        echo "No download workers are currently active."
    fi
}

case "$COMMAND" in
    start)
        start_single_worker "$WORKER_ID" "$NUM_WORKERS"
        ;;
    status)
        status_single_worker "$WORKER_ID" "$NUM_WORKERS"
        ;;
    stop)
        stop_single_worker "$WORKER_ID" "$NUM_WORKERS"
        ;;
    start-cluster)
        start_cluster "$COMMAND" "${2:-2}"
        ;;
    status-all)
        status_all_workers
        ;;
    stop-all)
        stop_all_workers
        ;;
    *)
        echo "Usage: $0 {start|status|stop|start-cluster|status-all|stop-all} [worker_id|cluster_size] [num_workers]"
        exit 1
        ;;
esac
