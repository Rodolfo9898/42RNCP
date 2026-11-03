#!/bin/sh
# Builds the 42Cursus repo: one submodule per project, grouped by track like samples/ (common-core, post-common-core, rncp).
#   init                    create the local repo (next to this one) and the GitHub repo; safe to run again
#   sort [name=track ...]   make every git repo in the projects folder a submodule under its track's folder, then commit
#   update                  move every submodule to the newest commit of its own repository and commit the new positions
# The track comes from the subject PDFs in samples/: a project named like a PDF (libft -> libft.pdf) goes in that PDF's
# folder. A project with any other name needs name=track (e.g. ft_transcendence=common-core).
# Nothing is pushed by `sort` or `update`; push 42Cursus yourself once you are happy with it (or CURSUS_PUSH=1 for `update`).
# Settings (environment): CURSUS_REPO (Rodolfo9898/42Cursus), CURSUS_DIR (a folder named like the repo, next to this one),
# CURSUS_VISIBILITY (private or public), PROJECTS_DIR (./projects), CURSUS_PUSH (1: `update` also pushes).
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

# Moves every project (submodule) of 42Cursus to the newest commit of its own repository, then commits the new positions.
# A project whose folder has uncommitted changes, or commits that are not on its origin, is skipped, never overwritten.
update_projects() {
    [ -d "$dir/.git" ] || die "$dir does not exist yet: run init first"
    listing=$(mktemp) || exit 1
    # (the projects are the gitlinks of the index: unlike .gitmodules this keeps a folder name with a space in one piece)
    git -C "$dir" -c core.quotepath=off ls-files -s 2>/dev/null | grep '^160000 ' | cut -f2- > "$listing"
    if [ ! -s "$listing" ]; then
        rm -f "$listing"
        echo "cursus: no projects in $dir yet: run sort first"
        return 0
    fi
    # Positions recorded by other machines first, but only when that cannot touch anything of yours.
    if git -C "$dir" rev-parse -q --verify '@{u}' >/dev/null 2>&1 && [ -z "$(git -C "$dir" status --porcelain 2>/dev/null)" ]; then
        git -C "$dir" pull -q --ff-only >/dev/null 2>&1 || echo "warn 42Cursus: could not fast-forward from origin (continuing with the local copy)"
    fi
    git -C "$dir" submodule sync -q --recursive >/dev/null 2>&1
    set --
    failed=0
    skipped=0
    kept=0
    while IFS= read -r path; do
        old=$(git -C "$dir" rev-parse -q --verify "HEAD:$path" 2>/dev/null)
        if [ ! -e "$dir/$path/.git" ]; then       # a fresh clone of 42Cursus: the project is not checked out yet
            git -C "$dir" submodule update -q --init -- "$path" >/dev/null 2>&1 || { echo "fail $path: could not fetch it" >&2; failed=$((failed + 1)); continue; }
        fi
        if [ -n "$(git -C "$dir/$path" status --porcelain 2>/dev/null)" ]; then
            echo "skip $path: it has uncommitted changes"; skipped=$((skipped + 1)); continue
        fi
        git -C "$dir/$path" fetch -q origin >/dev/null 2>&1 || { echo "fail $path: could not fetch from its origin (network, or the ssh key?)" >&2; failed=$((failed + 1)); continue; }
        if [ -z "$(git -C "$dir/$path" branch -r --contains HEAD 2>/dev/null)" ]; then
            echo "skip $path: it has commits that are not on its origin (push them first)"; skipped=$((skipped + 1)); continue
        fi
        git -C "$dir" submodule update -q --init --remote -- "$path" >/dev/null 2>&1 || { echo "fail $path: could not move it to the newest commit" >&2; failed=$((failed + 1)); continue; }
        new=$(git -C "$dir/$path" rev-parse HEAD)
        if [ "$new" = "$old" ]; then
            kept=$((kept + 1)); echo "ok   $path: already the newest ($(git -C "$dir/$path" rev-parse --short HEAD))"
        else
            count=$(git -C "$dir/$path" rev-list --count "$old..$new" 2>/dev/null)
            echo "up   $path: $(printf '%.7s' "$old") -> $(printf '%.7s' "$new")${count:+ ($count new commit(s))}"
            set -- "$@" "$path"
        fi
    done < "$listing"
    rm -f "$listing"
    if [ $# -gt 0 ]; then
        git -C "$dir" commit -q -m "Update $# project(s)" -m "$*" -- "$@" || exit 1     # only these paths, never something else that is staged
        echo "cursus: committed the new position of $# project(s)"
        if [ "${CURSUS_PUSH:-}" = 1 ]; then
            git -C "$dir" push -q || die "could not push 42Cursus"
            echo "cursus: pushed"
        else
            echo "cursus: push with: git -C $dir push   (or run again with CURSUS_PUSH=1)"
        fi
    else
        echo "cursus: nothing to update"
    fi
    [ "$skipped" -eq 0 ] || echo "cursus: $skipped project(s) skipped, see above"
    [ "$failed" -eq 0 ] || die "$failed project(s) could not be updated, see above"
}

cmd=${1:-}
[ $# -gt 0 ] && shift
case $cmd in
    init) init ;;
    update) update_projects ;;
    sort)
        for o in "$@"; do
            case $o in *=*) ;; *) die "expected name=track, got '$o'" ;; esac
            case " $tracks " in *" ${o#*=} "*) ;; *) die "unknown track '${o#*=}' (use: $tracks)" ;; esac
        done
        overrides="$*"
        sort_projects ;;
    *) echo "usage: cursus.sh init | sort [name=track ...] | update" >&2; exit 2 ;;
esac
