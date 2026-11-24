#!/bin/sh
# Fetches norminette from its official repository at a pinned tag and refuses to continue if the
# commit is not the one we reviewed. Prefers SSH (a forwarded agent), falls back to HTTPS.
set -eu

dest="${NORMINETTE_DEST:-/src}"
clone() {
    git -c advice.detachedHead=false clone --depth 1 --branch "$NORMINETTE_REF" "$1" "$dest"
}

if [ -n "${SSH_AUTH_SOCK:-}" ] && ssh-add -l >/dev/null 2>&1; then
    # Trust GitHub's published ED25519 host key only, not whatever answers first.
    mkdir -p -m 700 "$HOME/.ssh"
    ssh-keyscan -t ed25519 github.com > /tmp/github.key 2>/dev/null
    fingerprint=$(ssh-keygen -lf /tmp/github.key | awk '{print $2}')
    if [ "$fingerprint" != "$GITHUB_ED25519_FINGERPRINT" ]; then
        echo "unexpected GitHub host key: $fingerprint" >&2
        exit 1
    fi
    cp /tmp/github.key "$HOME/.ssh/known_hosts"
    echo "cloning norminette over SSH" >&2
    clone "$NORMINETTE_REPO"
else
    echo "no ssh-agent available during the build: cloning norminette over HTTPS" >&2
    clone "$NORMINETTE_HTTPS"
fi

actual=$(git -C "$dest" rev-parse HEAD)
if [ "$actual" != "$NORMINETTE_COMMIT" ]; then
    echo "norminette $NORMINETTE_REF is at $actual, expected $NORMINETTE_COMMIT" >&2
    exit 1
fi
