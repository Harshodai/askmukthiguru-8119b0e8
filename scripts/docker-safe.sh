#!/usr/bin/env bash
# docker-safe.sh
# Temporary Docker config helper that strips credential store keys
# from ~/.docker/config.json during builds to avoid macOS keychain
# errors (-25293) from Docker Desktop's credential helper.
#
# Usage: scripts/docker-safe.sh <docker-command> [args...]
# Example: scripts/docker-safe.sh docker compose up -d --build frontend

set -e

# Support custom macOS Docker binary path
CUSTOM_DOCKER_BIN="/Users/harshodaikolluru/.docker/bin"
if [[ -d "$CUSTOM_DOCKER_BIN" ]]; then
    export PATH="$CUSTOM_DOCKER_BIN:$PATH"
fi

DOCKER_CONFIG_FILE="${HOME}/.docker/config.json"

# Fallback: if no credentials file exists, just run the command as-is
if [[ ! -f "$DOCKER_CONFIG_FILE" ]]; then
    exec "$@"
fi

# Backup the original config
BAK=$(mktemp)
cp "$DOCKER_CONFIG_FILE" "$BAK"

# Function to restore original config on exit (success, failure, or interrupt)
__restore() {
    cp "$BAK" "$DOCKER_CONFIG_FILE"
    rm -f "$BAK"
}
trap __restore EXIT

# Strip credential store keys (requires python3, available on all modern macOS/Docker Desktop)
python3 -c "
import json;
d = json.load(open('$BAK'))
for key in list(d.keys()):
    if key.lower() in ('credsstore', 'credstore'):
        d.pop(key)
json.dump(d, open('$DOCKER_CONFIG_FILE', 'w'), indent='\t')
"

# Run the command
exec "$@"
