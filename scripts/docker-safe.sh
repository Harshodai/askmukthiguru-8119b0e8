#!/usr/bin/env bash
# docker-safe.sh
# Bypasses macOS keychain credentials helper error (-25293)
# by pointing Docker to a clean configuration directory.

set -e

# Support custom macOS Docker binary path
CUSTOM_DOCKER_BIN="/Users/harshodaikolluru/.docker/bin"
if [[ -d "$CUSTOM_DOCKER_BIN" ]]; then
    export PATH="$CUSTOM_DOCKER_BIN:$PATH"
fi

# Define clean docker config directory in the workspace
WORKSPACE_DIR="/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8"
CLEAN_DIR="${WORKSPACE_DIR}/.docker_clean"
mkdir -p "$CLEAN_DIR"

# Write config that disables credsStore/keychain helper
echo '{"credsStore": ""}' > "${CLEAN_DIR}/config.json"

# Symlink Host CLI plugins and contexts so compose command flags work
HOST_DOCKER_DIR="${HOME}/.docker"
if [[ -d "${HOST_DOCKER_DIR}/cli-plugins" ]]; then
    ln -sf "${HOST_DOCKER_DIR}/cli-plugins" "${CLEAN_DIR}/cli-plugins"
fi
if [[ -d "${HOST_DOCKER_DIR}/contexts" ]]; then
    ln -sf "${HOST_DOCKER_DIR}/contexts" "${CLEAN_DIR}/contexts"
fi

# Export clean config path
export DOCKER_CONFIG="$CLEAN_DIR"

# Run the command
exec "$@"
