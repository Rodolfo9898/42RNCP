#!/bin/sh
# Stops the standalone Apple Claude Code proxy, but only if scripts/apple/apple-setup.sh started it (a proxy you started yourself stays).
# `make clean` and `make fclean` run this on a Mac. Nothing to do on Linux, where the marker never exists.
marker=".apple-proxy-started"
[ -f "$marker" ] || exit 0
rm -f "$marker"
"${APPLE_CLAUDE:-claude}" --kill-standalone-proxy >/dev/null 2>&1 && echo "apple: standalone proxy stopped." \
    || echo "apple: could not stop the standalone proxy; run: claude --kill-standalone-proxy" >&2
