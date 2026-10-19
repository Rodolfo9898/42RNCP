#!/bin/sh
# Starts as root only long enough to make the host's ssh-agent usable by the unprivileged app user.
#
# Docker Desktop exposes the agent as a root-owned socket that uid 1000 often cannot open.
# A tiny relay (socat) owned by root re-publishes it with mode 666, then we drop privileges.
# On Linux the mounted socket is the host user's own (uid 1000): the app uses it directly, because root without
# CAP_DAC_OVERRIDE could not open it for the relay anyway.
# Every step is best-effort: if anything fails, the app still starts and the UI explains why SSH is unavailable.
HOST_SOCK="${HOST_SSH_SOCK:-/run/host-services/ssh-auth.sock}"
PROXY_SOCK="${PROXY_SSH_SOCK:-/tmp/ssh-agent.sock}"
APP_UID="${APP_UID:-1000}"

if [ "$(id -u)" = "0" ]; then
    if [ -S "$HOST_SOCK" ] && [ "$(stat -c %u "$HOST_SOCK" 2>/dev/null)" = "$APP_UID" ]; then
        :
    elif [ -S "$HOST_SOCK" ] && command -v socat >/dev/null 2>&1; then
        rm -f "$PROXY_SOCK"
        socat "UNIX-LISTEN:$PROXY_SOCK,fork,mode=666" "UNIX-CONNECT:$HOST_SOCK" &
        i=0
        while [ ! -S "$PROXY_SOCK" ] && [ "$i" -lt 20 ]; do
            sleep 0.1
            i=$((i + 1))
        done
        if [ -S "$PROXY_SOCK" ]; then
            export SSH_AUTH_SOCK="$PROXY_SOCK"
        else
            echo "entrypoint: ssh-agent relay did not start; using the host socket directly" >&2
        fi
    fi
    exec setpriv --reuid="$APP_UID" --regid="$APP_UID" --clear-groups "$@"
fi
exec "$@"
