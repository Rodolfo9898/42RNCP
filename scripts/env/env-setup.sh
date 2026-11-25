#!/bin/sh
# Makes sure .env exists and holds the secrets the containers need (called by `make token`, so by every `make build` / `make run`).
#
#   - No .env yet: it is a copy of .env.example, so it has the example's structure, comments and options.
#   - A secret that is missing (TERMINAL_TOKEN, EDITOR_TOKEN, SCRAPER_TOKEN) is filled in on its own line of the example (`# TERMINAL_TOKEN=` becomes
#     `TERMINAL_TOKEN=<random>`). Nothing else is moved or rewritten, and a value that is already there is never changed.
#   - An .env that was not made from the example (no such line) gets the secret appended at the end.
set -eu

env_file="${1:-.env}"
example="${2:-.env.example}"

if [ ! -f "$env_file" ]; then
	if [ -f "$example" ]; then
		cp "$example" "$env_file"
		echo "created $env_file from $example"
	else
		: > "$env_file"
	fi
fi
chmod 600 "$env_file"

fill() {
	name="$1"
	if grep -q "^$name=." "$env_file"; then
		return 0
	fi
	value="$(openssl rand -hex 24)"
	if grep -Eq "^(# ?)?$name=$" "$env_file"; then
		# the example's own line (commented out, or empty): same place, now with a value
		awk -v name="$name" -v value="$value" '
			!done && $0 ~ ("^(# ?)?" name "=$") { print name "=" value; done = 1; next }
			{ print }' "$env_file" > "$env_file.new"
		cat "$env_file.new" > "$env_file"       # (not mv: the file keeps its mode and owner)
		rm -f "$env_file.new"
	else
		if [ -s "$env_file" ] && [ -n "$(tail -c1 "$env_file")" ]; then printf '\n' >> "$env_file"; fi     # end the last line first
		printf '%s=%s\n' "$name" "$value" >> "$env_file"
	fi
	echo "created $name in $env_file"
}

fill TERMINAL_TOKEN
fill EDITOR_TOKEN
fill SCRAPER_TOKEN
