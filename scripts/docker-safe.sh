#!/usr/bin/env bash
# docker-safe.sh
# Bypasses macOS keychain credentials helper error (-25293)
# by mocking the credential helper binaries.

set -e

# Define clean docker config directory in the workspace
WORKSPACE_DIR="/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8"
CLEAN_DIR="${WORKSPACE_DIR}/.docker_clean"
CLEAN_BIN="${CLEAN_DIR}/bin"
mkdir -p "$CLEAN_BIN"

link_host_dir() {
    local source="$1"
    local target="$2"
    if [[ -L "$target" ]]; then
        if [[ "$(readlink "$target")" == "$source" ]]; then
            return 0
        fi
        rm -f "$target" # Remove only the stale symlink, never its referent.
    elif [[ -e "$target" ]]; then
        echo "Refusing to replace non-symlink Docker config path: $target" >&2
        return 1
    fi
    ln -s "$source" "$target"
}

# Write mock credential helpers that bypass the locked macOS keychain
for helper in docker-credential-osxkeychain docker-credential-desktop; do
    cat << 'EOF' > "${CLEAN_BIN}/${helper}"
#!/usr/bin/env bash
# Mock credential helper to bypass locked macOS keychain
echo "credentials not found in native keychain"
exit 1
EOF
    chmod +x "${CLEAN_BIN}/${helper}"
done

# Prepend mock bin path and custom macOS Docker binary path to PATH
CUSTOM_DOCKER_BIN="/Users/harshodaikolluru/.docker/bin"
export PATH="${CLEAN_BIN}:${CUSTOM_DOCKER_BIN}:${PATH}"

# Write config that disables credsStore/keychain helper
echo '{"credsStore": ""}' > "${CLEAN_DIR}/config.json"

# Symlink Host CLI plugins and contexts so compose command flags work
HOST_DOCKER_DIR="${HOME}/.docker"
if [[ -d "${HOST_DOCKER_DIR}/cli-plugins" ]]; then
    link_host_dir "${HOST_DOCKER_DIR}/cli-plugins" "${CLEAN_DIR}/cli-plugins"
fi
if [[ -d "${HOST_DOCKER_DIR}/contexts" ]]; then
    link_host_dir "${HOST_DOCKER_DIR}/contexts" "${CLEAN_DIR}/contexts"
fi

# Export clean config path
export DOCKER_CONFIG="$CLEAN_DIR"

# Run the command
exec "$@"
