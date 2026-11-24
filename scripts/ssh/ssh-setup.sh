#!/bin/sh
# Called by `make`: makes sure an ssh-agent is running at $1 and holds your SSH keys, so the web container can clone
# with them. The private keys never leave this computer: the container only gets the agent's socket.
#   $1        the agent socket (your $SSH_AUTH_SOCK, or the one this script starts)
#   $2 ...    the private keys to load (default: ~/.ssh/id_* that are not .pub)
# Never fails the build: without a usable agent the app still starts and its status bar says why SSH is not ready.
sock="$1"
shift
[ -n "$sock" ] || { echo "ssh: no agent socket given" >&2; exit 0; }
export SSH_AUTH_SOCK="$sock"

ssh-add -l >/dev/null 2>&1
if [ $? -eq 2 ]; then
    if [ "${VERDICT_OWN_AGENT:-}" = "1" ]; then
        rm -f "$sock"
        mkdir -p "$(dirname "$sock")"
        if ssh-agent -a "$sock" >/dev/null; then
            echo "ssh: started an ssh-agent at $sock"
        fi
    fi
    ssh-add -l >/dev/null 2>&1
    if [ $? -eq 2 ]; then
        echo "ssh: cannot reach the ssh-agent at $sock; cloning will not work until one is running." >&2
        if [ "${VERDICT_OWN_AGENT:-}" != "1" ]; then
            echo "     Start one (eval \"\$(ssh-agent)\"), or unset SSH_AUTH_SOCK to let make start its own, then run make again." >&2
        fi
        exit 0
    fi
fi

[ $# -gt 0 ] || set -- $(ls "$HOME"/.ssh/id_* 2>/dev/null | grep -v '\.pub$')
loaded=$(ssh-add -l 2>/dev/null)
for key in "$@"; do
    [ -f "$key" ] || continue
    fp=$(ssh-keygen -lf "$key.pub" 2>/dev/null | awk '{print $2}')
    if [ -n "$fp" ] && printf '%s\n' "$loaded" | grep -qF "$fp"; then
        continue
    fi
    echo "ssh: adding $key to the agent"
    ssh-add "$key" || echo "ssh: could not add $key (wrong passphrase?)" >&2
done

count=$(ssh-add -l 2>/dev/null | grep -c .)
if [ "$count" -gt 0 ]; then
    echo "ssh: $count key(s) in the agent, available to the web container"
else
    echo "ssh: the agent holds no keys; put a key in ~/.ssh (or pass SSH_KEYS=...) and run make again." >&2
fi
exit 0
