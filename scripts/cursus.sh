#!/bin/sh
# Builds the 42Cursus repo: one submodule per project, grouped by track like samples/ (common-core, post-common-core, rncp).
#   init                    create the local repo (next to this one) and the GitHub repo; safe to run again
#   sort [name=track ...]   make every git repo in the projects folder a submodule under its track's folder, then commit
# The track comes from the subject PDFs in samples/: a project named like a PDF (libft -> libft.pdf) goes in that PDF's
# folder. A project with any other name needs name=track (e.g. ft_transcendence=common-core).
# Nothing is pushed by `sort`; push 42Cursus yourself once you are happy with it.
# Settings (environment): CURSUS_REPO (Rodolfo9898/42Cursus), CURSUS_DIR (a folder named like the repo, next to this one),
# CURSUS_VISIBILITY (private or public), PROJECTS_DIR (./projects).
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root" || exit 1
repo=${CURSUS_REPO:-Rodolfo9898/42Cursus}
dir=${CURSUS_DIR:-$(dirname "$root")/$(basename "$repo")}
visibility=${CURSUS_VISIBILITY:-private}
projects=${PROJECTS_DIR:-./projects}
tracks="common-core post-common-core rncp"
overrides=

die() { echo "cursus: $*" >&2; exit 1; }

# "Ft_Printf", "ft-printf" and "ft_printf.pdf" all compare equal.
key() { printf '%s' "$1" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9'; }

# Prints the track of project $1: an explicit name=track first, then the folder of the subject PDF with that name.
track_of() {
    k=$(key "$1")
    for o in $overrides; do
        [ "$(key "${o%%=*}")" = "$k" ] && { echo "${o#*=}"; return 0; }
    done
    for t in $tracks; do
        for pdf in samples/$t/*; do
            [ -f "$pdf" ] || continue
            [ "$(key "$(basename "$pdf" .pdf)")" = "$k" ] && { echo "$t"; return 0; }
        done
    done
    return 1
}

init() {
    command -v git >/dev/null || die "git is not installed"
    case $visibility in private|public) ;; *) die "CURSUS_VISIBILITY must be private or public" ;; esac
    if ! git -C "$dir" remote get-url origin >/dev/null 2>&1; then
        command -v gh >/dev/null || die "the GitHub CLI is needed to create $repo: brew install gh && gh auth login"
        gh auth status >/dev/null 2>&1 || die "the GitHub CLI is not logged in: gh auth login"
    fi

    mkdir -p "$dir" || exit 1
    [ -d "$dir/.git" ] || git -C "$dir" init -q -b main || exit 1
    if [ ! -f "$dir/README.md" ]; then
        cat > "$dir/README.md" <<EOF
# $(basename "$repo")

My 42 projects, one submodule each, grouped by track:

- \`common-core/\`
- \`post-common-core/\`
- \`rncp/\`

Clone everything with \`git clone --recurse-submodules git@github.com:$repo.git\`.
EOF
    fi
    git -C "$dir" rev-parse -q --verify HEAD >/dev/null 2>&1 || {
        git -C "$dir" add README.md && git -C "$dir" commit -q -m "Initial commit" || exit 1
    }

    if ! git -C "$dir" remote get-url origin >/dev/null 2>&1; then
        if gh repo view "$repo" >/dev/null 2>&1; then
            echo "cursus: $repo already exists on GitHub, using it"
        else
            gh repo create "$repo" "--$visibility" --description "My 42 projects, as submodules" || exit 1
        fi
        git -C "$dir" remote add origin "git@github.com:$repo.git" || exit 1
    fi
    git -C "$dir" push -u origin main || exit 1
    echo "cursus: $repo is ready ($visibility), local copy in $dir"
}

sort_projects() {
    [ -d "$dir/.git" ] || die "$dir does not exist yet: run init first"
    [ -d "$projects" ] || die "no projects folder at $projects"
    added=0
    names=
    for p in "$projects"/*/; do
        [ -d "$p" ] || continue
        name=$(basename "$p")
        [ -e "$p/.git" ] || { echo "skip $name: not a git repository"; continue; }
        url=$(git -C "$p" remote get-url origin 2>/dev/null) || { echo "skip $name: no origin remote, a submodule needs a URL"; continue; }
        track=$(track_of "$name") || { echo "skip $name: no subject PDF with this name; run again with $name=<track>"; continue; }
        [ -e "$dir/$track/$name" ] && { echo "ok   $name: already in $track/"; continue; }

        # The submodule is cloned from the URL, so it holds what origin has, not this folder's local work.
        ahead=$(git -C "$p" rev-list --count '@{u}..HEAD' 2>/dev/null)
        if [ "${ahead:-0}" -gt 0 ] || [ -n "$(git -C "$p" status --porcelain 2>/dev/null)" ]; then
            echo "warn $name: unpushed commits or uncommitted changes; the submodule will only have what origin has"
        fi
        mkdir -p "$dir/$track"
        git -C "$dir" submodule add -q "$url" "$track/$name" || { echo "fail $name: could not add $url" >&2; continue; }
        echo "add  $name -> $track/"
        added=$((added + 1))
        names="$names $name"
    done
    if [ "$added" -gt 0 ]; then
        git -C "$dir" commit -q -m "Add $added project(s)" -m "$names" || exit 1
        echo "cursus: committed $added project(s); push with: git -C $dir push"
    else
        echo "cursus: nothing to add"
    fi
}

cmd=${1:-}
[ $# -gt 0 ] && shift
case $cmd in
    init) init ;;
    sort)
        for o in "$@"; do
            case $o in *=*) ;; *) die "expected name=track, got '$o'" ;; esac
            case " $tracks " in *" ${o#*=} "*) ;; *) die "unknown track '${o#*=}' (use: $tracks)" ;; esac
        done
        overrides="$*"
        sort_projects ;;
    *) echo "usage: cursus.sh init | sort [name=track ...]" >&2; exit 2 ;;
esac
