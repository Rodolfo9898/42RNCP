#!/bin/sh
# On a Mac, claude in the terminal container goes through Apple Claude Code on this Mac (your AppleConnect sign-in) instead of a personal
# Claude login. `make run` runs this first, and stops when a step fails: there is no quiet fallback to the other login.
#   1. this Mac has Apple Claude Code (not the plain claude)
#   2. you are signed in with AppleConnect: the sign-in window opens here when you are not (the token is read and thrown away, never shown)
#   3. Apple Claude Code's own health check passes (sign-in, certificates, the Floodgate gateway)
#   4. its proxy answers on 127.0.0.1:$APPLE_PROXY_PORT (the standalone one, port 18281, is started when nothing answers there)
#   5. a one-token request through that proxy works: the proof that the container's claude will work too
# Used by the Makefile only on a Mac (HOST_OS=Darwin). Linux never gets here.
set -u

claude="${APPLE_CLAUDE:-claude}"
port="${APPLE_PROXY_PORT:-18281}"
url="http://127.0.0.1:$port"
marker=".apple-proxy-started"          # present only when THIS script started the standalone proxy (scripts/apple/apple-stop.sh reads it)
config="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

fail() {
    echo "apple: $1" >&2
    echo "apple: stopped. On a Mac the editor's claude only runs through your Apple sign-in; nothing was started." >&2
    exit 1
}

# 1 ---------------------------------------------------------------------------------------------------------------------------
version=$("$claude" --version 2>&1) || fail "cannot run '$claude'. Install Apple Claude Code on this Mac."
case "$version" in
    *@apple/claude-code*) ;;
    *) fail "'$claude' is not Apple Claude Code (it says: $(printf '%s' "$version" | head -n 1)). The Apple route needs the work build." ;;
esac

# 2 ---------------------------------------------------------------------------------------------------------------------------
# The command Apple Claude Code itself uses to get your token (settings.json, apiKeyHelper). It opens the AppleConnect window when needed.
helper=$(sed -n 's/.*"apiKeyHelper"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$config/settings.json" 2>/dev/null | head -n 1)
[ -n "$helper" ] || fail "no apiKeyHelper in $config/settings.json. Run: claude setup"
echo "apple: signing in with AppleConnect (a window may open)..."
sh -c "$helper" >/dev/null || fail "AppleConnect sign-in failed. Check the Apple VPN, then run make again."

# 3 ---------------------------------------------------------------------------------------------------------------------------
esc=$(printf '\033')
report=$("$claude" diagnose 2>&1 | sed "s/${esc}\[[0-9;]*m//g")
printf '%s\n' "$report" | grep -q 'All checks passed' || {
    printf '%s\n' "$report" | tail -n 15 >&2
    fail "'claude diagnose' did not pass (above). Fix that first."
}

# 4 ---------------------------------------------------------------------------------------------------------------------------
answers() { curl -s -o /dev/null --noproxy '*' -m 3 "$url/"; }       # exit 0 when anything answers HTTP, whatever the status
if ! answers; then
    [ "$port" = 18281 ] || fail "nothing answers on port $port. That is the proxy of an Apple Claude Code session: keep that session open, or remove APPLE_PROXY_PORT."
    echo "apple: starting Apple Claude Code's standalone proxy on 127.0.0.1:18281..."
    "$claude" --start-standalone-proxy >/dev/null 2>&1
    : > "$marker"
    waited=0
    until answers; do
        waited=$((waited + 1))
        [ "$waited" -le 20 ] || fail "the standalone proxy did not start (see $config/apple/standalone/standalone.log)."
        sleep 1
    done
fi

# 5 ---------------------------------------------------------------------------------------------------------------------------
# The key is a placeholder: the proxy adds the real sign-in. One token of output, on the smallest model.
code=$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' -m 60 \
    -H 'x-api-key: floodgate' -H 'anthropic-version: 2023-06-01' -H 'content-type: application/json' \
    -d '{"model":"claude-haiku-5-5","max_tokens":1,"messages":[{"role":"user","content":"ok"}]}' "$url/v1/messages")
[ "$code" = 200 ] || fail "the proxy on port $port answered HTTP ${code:-none} to a test request (200 expected). Look in $config/apple/logs/."

echo "apple: ready. claude in the editor uses your AppleConnect sign-in, through $url."
