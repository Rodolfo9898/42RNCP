#!/bin/sh
# Maintains the 42Cursus repo: one submodule per project, grouped by track like samples/ (common-core, post-common-core, rncp).
# GitHub is the only copy. Nothing of 42Cursus is kept on this machine: each command clones it from GitHub into a temporary folder,
# works there, pushes the result and deletes the folder. The projects are never cloned either: a submodule is a project's URL plus
# the commit it is at, and the newest commit of a project is read from GitHub (git ls-remote).
#   init                    create the GitHub repo (and its first commit) if it does not exist yet; safe to run again
#   sort [name=track ...]   add every git repo of the projects folder as a submodule under its track's folder, then push; a
#                           folder that only holds git repos (cpp-modules/cpp00 ...) keeps that folder: common-core/cpp-modules/cpp00
#   update                  move every submodule to the newest commit of its own repository, then push
#   push [name ...]         push the projects (all of the projects folder, or the ones named) to their own GitHub repos
#   refresh [name ...]      pull the projects (all of the projects folder, or the ones named) from their own GitHub repos
# The track comes from the subject PDFs in samples/: a project named like a PDF (libft -> libft.pdf) goes in that PDF's
# folder. A project with any other name needs name=track (e.g. ft_transcendence=common-core).
# A submodule holds what a project's GitHub repo has, not your local folder: run `push` first so that `sort` and `update` see your
# latest work.
# Settings (environment): CURSUS_REPO (Rodolfo9898/42Cursus), CURSUS_URL (git@github.com:<CURSUS_REPO>.git), CURSUS_VISIBILITY
# (private or public), PROJECTS_DIR (./projects), CURSUS_DRY_RUN (1: do everything except pushing, pulling and creating).
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root" || exit 1
repo=${CURSUS_REPO:-Rodolfo9898/42Cursus}
cursus_url=${CURSUS_URL:-git@github.com:$repo.git}
visibility=${CURSUS_VISIBILITY:-private}
projects=${PROJECTS_DIR:-./projects}
tracks="common-core post-common-core rncp"
overrides=
# The URLs come from repositories other people wrote: no `ext::` (it runs a command) and nothing else exotic.
export GIT_ALLOW_PROTOCOL=${GIT_ALLOW_PROTOCOL:-file:git:http:https:ssh}
dry=0
[ "${CURSUS_DRY_RUN:-}" = 1 ] && dry=1

tmp=
cleanup() { if [ -n "$tmp" ]; then rm -rf "$tmp"; fi; }
trap cleanup EXIT
trap 'exit 130' INT TERM

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

# Prints the commit at the tip of the repository at URL $1 (its default branch, or branch $2), read from GitHub without cloning it.
newest() {
    case $1 in -*) return 1 ;; esac
    if [ -n "$2" ]; then ref="refs/heads/$2"; else ref=HEAD; fi
    git ls-remote "$1" "$ref" 2>/dev/null | cut -f1 | head -n 1
}

# Clones 42Cursus from GitHub into a temporary folder ($work). Its projects are not checked out: they are not needed.
clone_cursus() {
    command -v git >/dev/null || die "git is not installed"
    if ! out=$(git ls-remote "$cursus_url" HEAD 2>&1); then
        die "cannot reach $cursus_url: $(printf '%s' "$out" | tail -n 1) (does it exist? run: make cursus; is your ssh key loaded?)"
    fi
    [ -n "$out" ] || die "$repo has no commits yet: run: make cursus"
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/cursus.XXXXXX") || exit 1
    work=$tmp/42Cursus
    git clone -q "$cursus_url" "$work" || die "could not clone $cursus_url"
}

# Pushes what was committed in $work to GitHub.
publish() {
    if [ "$dry" -eq 1 ]; then
        echo "cursus: dry run, nothing pushed ($1)"
        return 0
    fi
    git -C "$work" push -q origin HEAD || die "could not push to $repo (did something else push meanwhile? run it again; or the ssh key?)"
    echo "cursus: pushed to $repo ($1)"
}

# Prints setting $2 (url, branch) of the submodule that lives at path $1, from the .gitmodules of $work.
module_setting() {
    git -C "$work" config -f .gitmodules --name-only --get-regexp '^submodule\..*\.path$' 2>/dev/null | while IFS= read -r setting; do
        [ "$(git -C "$work" config -f .gitmodules --get "$setting")" = "$1" ] || continue
        name=${setting#submodule.}
        git -C "$work" config -f .gitmodules --get "submodule.${name%.path}.$2"
        break
    done
}

init() {
    command -v git >/dev/null || die "git is not installed"
    case $visibility in private|public) ;; *) die "CURSUS_VISIBILITY must be private or public" ;; esac
    if out=$(git ls-remote "$cursus_url" HEAD 2>/dev/null); then
        if [ -n "$out" ]; then
            echo "cursus: $repo is ready on GitHub"
            return 0
        fi
        echo "cursus: $repo exists on GitHub but is empty, adding its first commit"
    else
        if [ "$dry" -eq 1 ]; then
            echo "cursus: dry run, would create $repo ($visibility) on GitHub"
            return 0
        fi
        command -v gh >/dev/null || die "the GitHub CLI is needed to create $repo: brew install gh && gh auth login"
        gh auth status >/dev/null 2>&1 || die "the GitHub CLI is not logged in: gh auth login"
        if gh repo view "$repo" >/dev/null 2>&1; then
            die "$repo exists but $cursus_url cannot be read (is your ssh key loaded?)"
        fi
        gh repo create "$repo" "--$visibility" --description "My 42 projects, as submodules" || exit 1
    fi

    tmp=$(mktemp -d "${TMPDIR:-/tmp}/cursus.XXXXXX") || exit 1
    work=$tmp/42Cursus
    git init -q -b main "$work" || exit 1
    cat > "$work/README.md" <<EOF
# $(basename "$repo")

My 42 projects, one submodule each, grouped by track:

- \`common-core/\`
- \`post-common-core/\`
- \`rncp/\`

Clone everything with \`git clone --recurse-submodules git@github.com:$repo.git\`.
EOF
    git -C "$work" add README.md && git -C "$work" commit -q -m "Initial commit" || die "could not commit (git config user.name and user.email?)"
    git -C "$work" remote add origin "$cursus_url" || exit 1
    if [ "$dry" -eq 1 ]; then
        echo "cursus: dry run, nothing pushed (first commit)"
        return 0
    fi
    git -C "$work" push -q -u origin main || die "could not push the first commit to $repo"
    echo "cursus: $repo is ready ($visibility)"
}

# A group is a folder of the projects folder that is not a git repository itself but holds some (e.g. cpp-modules/ with cpp00/,
# cpp01/...). Prints the git repositories directly inside folder $1, one name per line.
group_members() {
    for c in "$1"/*/; do
        [ -e "$c/.git" ] && basename "$c"
    done
}

# Prints the track of group $1 (folder $2): an explicit name=track for the group first, then the track of the first of its
# repositories that has one (cpp-modules -> cpp00 -> common-core). Every repository of the group goes in that track.
group_track() {
    k=$(key "$1")
    for o in $overrides; do
        [ "$(key "${o%%=*}")" = "$k" ] && { echo "${o#*=}"; return 0; }
    done
    for m in $(group_members "$2"); do
        track_of "$m" && return 0
    done
    track_of "$1"
}

# Adds the repository at folder $1, shown as $2, as the submodule at path $3 of $work. Counts in added, failed and names.
add_one() {
    repo_dir=$1 label=$2 dest=$3
    url=$(git -C "$repo_dir" remote get-url origin 2>/dev/null) || { echo "skip $label: no origin remote, a submodule needs a URL"; return 0; }
    if [ -n "$(git -C "$work" ls-files -s -- ":(literal)$dest")" ]; then
        echo "ok   $label: already in ${dest%/*}/"; return 0
    fi

    # The submodule is the commit GitHub has, so local work that was not pushed is not in it.
    ahead=$(git -C "$repo_dir" rev-list --count '@{u}..HEAD' 2>/dev/null)
    if [ "${ahead:-0}" -gt 0 ] || [ -n "$(git -C "$repo_dir" status --porcelain 2>/dev/null)" ]; then
        echo "warn $label: unpushed commits or uncommitted changes; the submodule will only have what GitHub has (make cursus-push)"
    fi
    sha=$(newest "$url")
    if [ -z "$sha" ]; then
        echo "fail $label: could not read $url (network, the ssh key, or the repository has no commits)" >&2
        failed=$((failed + 1)); return 0
    fi
    git -C "$work" config -f .gitmodules "submodule.$dest.path" "$dest" &&
        git -C "$work" config -f .gitmodules "submodule.$dest.url" "$url" &&
        git -C "$work" update-index --add --cacheinfo 160000 "$sha" "$dest" || { echo "fail $label: could not add it" >&2; failed=$((failed + 1)); return 0; }
    echo "add  $label -> ${dest%/*}/ ($(printf '%.7s' "$sha"))"
    added=$((added + 1))
    names="$names
$dest"
}

sort_projects() {
    [ -d "$projects" ] || die "no projects folder at $projects"
    clone_cursus
    added=0
    failed=0
    names=
    for p in "$projects"/*/; do
        [ -d "$p" ] || continue
        p=${p%/}
        name=$(basename "$p")
        if [ -e "$p/.git" ]; then
            git -C "$p" remote get-url origin >/dev/null 2>&1 || { echo "skip $name: no origin remote, a submodule needs a URL"; continue; }
            track=$(track_of "$name") || { echo "skip $name: no subject PDF with this name; run again with $name=<track>"; continue; }
            add_one "$p" "$name" "$track/$name"
            continue
        fi
        members=$(group_members "$p")
        [ -n "$members" ] || { echo "skip $name: not a git repository"; continue; }
        track=$(group_track "$name" "$p") || { echo "skip $name/: none of its projects has a subject PDF; run again with $name=<track>"; continue; }
        for m in $members; do
            add_one "$p/$m" "$name/$m" "$track/$name/$m"
        done
    done
    if [ "$added" -gt 0 ]; then
        git -C "$work" add .gitmodules || exit 1
        git -C "$work" commit -q -m "Add $added project(s)" -m "${names#?}" || die "could not commit (git config user.name and user.email?)"
        publish "$added project(s) added"
    else
        echo "cursus: nothing to add"
    fi
    [ "$failed" -eq 0 ] || die "$failed project(s) could not be added, see above"
}

# Moves every project (submodule) of 42Cursus to the newest commit of its own repository, then commits and pushes the new positions.
update_projects() {
    clone_cursus
    listing=$tmp/gitlinks
    # (the projects are the gitlinks of the index: unlike .gitmodules this keeps a folder name with a space in one piece)
    git -C "$work" -c core.quotepath=off ls-files -s 2>/dev/null | grep '^160000 ' | cut -f2- > "$listing"
    if [ ! -s "$listing" ]; then
        echo "cursus: no projects in $repo yet: run: make cursus-sort"
        return 0
    fi
    set --
    failed=0
    skipped=0
    kept=0
    while IFS= read -r path; do
        old=$(git -C "$work" rev-parse -q --verify "HEAD:$path" 2>/dev/null)
        url=$(module_setting "$path" url)
        [ -n "$url" ] || { echo "skip $path: .gitmodules has no URL for it"; skipped=$((skipped + 1)); continue; }
        new=$(newest "$url" "$(module_setting "$path" branch)")
        if [ -z "$new" ]; then
            echo "fail $path: could not read the newest commit of its origin (network, or the ssh key?)" >&2
            failed=$((failed + 1)); continue
        fi
        if [ "$new" = "$old" ]; then
            kept=$((kept + 1)); echo "ok   $path: already the newest ($(printf '%.7s' "$new"))"
        elif git -C "$work" update-index --cacheinfo 160000 "$new" "$path"; then
            echo "up   $path: $(printf '%.7s' "$old") -> $(printf '%.7s' "$new")"
            set -- "$@" "$path"
        else
            echo "fail $path: could not record the new commit" >&2; failed=$((failed + 1))
        fi
    done < "$listing"
    if [ $# -gt 0 ]; then
        git -C "$work" commit -q -m "Update $# project(s)" -m "$(printf '%s\n' "$@")" || die "could not commit (git config user.name and user.email?)"
        echo "cursus: committed the new position of $# project(s)"
        publish "$# project(s) updated"
    else
        echo "cursus: nothing to update"
    fi
    [ "$skipped" -eq 0 ] || echo "cursus: $skipped project(s) skipped, see above"
    [ "$failed" -eq 0 ] || die "$failed project(s) could not be updated, see above"
}

# Prints the projects the arguments name, one per line: every folder of the projects folder when there are none, a group (a folder of repositories, e.g. cpp-modules) standing
# for each of its repositories (cpp-modules/cpp00 ...). A name given can be a project, a group, or group/project.
select_projects() {
    [ -d "$projects" ] || die "no projects folder at $projects"
    if [ $# -eq 0 ]; then
        for p in "$projects"/*/; do [ -d "$p" ] && set -- "$@" "$(basename "$p")"; done
    else
        for n in "$@"; do
            case $n in */*/* | .* | */.* | /* | */ | "") die "'$n' is not a project name (the name of a folder in $projects)" ;; esac
            [ -d "$projects/$n" ] || die "no project '$n' in $projects"
        done
    fi
    for n in "$@"; do
        members=
        [ -e "$projects/$n/.git" ] || members=$(group_members "$projects/$n")
        if [ -n "$members" ]; then
            for m in $members; do printf '%s/%s\n' "$n" "$m"; done
        else
            printf '%s\n' "$n"
        fi
    done
}

# Pushes the projects to their own GitHub repos (the current branch of each; never a force push), so that sort and update, which
# read GitHub, see them. Uncommitted changes are not pushed (they are not commits).
push_projects() {
    command -v git >/dev/null || die "git is not installed"
    list=$(select_projects "$@") || exit 1
    set --
    while IFS= read -r n; do
        [ -z "$n" ] || set -- "$@" "$n"
    done <<EOF
$list
EOF
    pushed=0
    failed=0
    for name in "$@"; do
        p=$projects/$name
        [ -e "$p/.git" ] || { echo "skip $name: not a git repository"; continue; }
        git -C "$p" remote get-url origin >/dev/null 2>&1 || { echo "skip $name: no origin remote to push to"; continue; }
        branch=$(git -C "$p" symbolic-ref -q --short HEAD) || { echo "skip $name: not on a branch (detached HEAD)"; continue; }
        if git -C "$p" rev-parse -q --verify '@{u}' >/dev/null 2>&1; then
            count=$(git -C "$p" rev-list --count '@{u}..HEAD' 2>/dev/null)
            how="push"
        else
            count=$(git -C "$p" rev-list --count HEAD --not --remotes=origin 2>/dev/null)     # a branch GitHub has not seen yet
            how="push -u origin $branch"
        fi
        dirty=
        [ -z "$(git -C "$p" status --porcelain 2>/dev/null)" ] || dirty=" (uncommitted changes are not pushed)"
        if [ "${count:-0}" -eq 0 ]; then
            echo "ok   $name: nothing to push$dirty"; continue
        fi
        if [ "$dry" -eq 1 ]; then
            echo "dry  $name: would push ${count:-0} commit(s) of $branch$dirty"; continue
        fi
        if out=$(git -C "$p" $how 2>&1); then
            echo "push $name: ${count:-0} commit(s) of $branch$dirty"
            pushed=$((pushed + 1))
        else
            echo "fail $name: not pushed: $(printf '%s' "$out" | tail -n 1) (never forced; git pull first if GitHub has commits you do not)" >&2
            failed=$((failed + 1))
        fi
    done
    [ "$pushed" -eq 0 ] || echo "cursus: pushed $pushed project(s); run: make cursus-update   to record their new commits in $repo"
    [ "$failed" -eq 0 ] || die "$failed project(s) could not be pushed, see above"
}

# Brings the projects up to date with their GitHub repos: the new commits of the current branch of each (the projects folder's, or the
# ones named) are fast-forwarded in. Nothing is merged and nothing of yours is overwritten: a project whose branch has commits GitHub
# does not, or whose uncommitted changes the new commits would touch, is reported and the others are still pulled.
refresh_projects() {
    command -v git >/dev/null || die "git is not installed"
    list=$(select_projects "$@") || exit 1
    set --
    while IFS= read -r n; do
        [ -z "$n" ] || set -- "$@" "$n"
    done <<EOF
$list
EOF
    pulled=0
    failed=0
    for name in "$@"; do
        p=$projects/$name
        [ -e "$p/.git" ] || { echo "skip $name: not a git repository"; continue; }
        git -C "$p" remote get-url origin >/dev/null 2>&1 || { echo "skip $name: no origin remote to pull from"; continue; }
        branch=$(git -C "$p" symbolic-ref -q --short HEAD) || { echo "skip $name: not on a branch (detached HEAD)"; continue; }
        git -C "$p" rev-parse -q --verify '@{u}' >/dev/null 2>&1 || { echo "skip $name: $branch has no upstream branch to pull"; continue; }
        if ! out=$(git -C "$p" fetch -q 2>&1); then
            echo "fail $name: could not fetch: $(printf '%s' "$out" | head -n 1) (network, or the ssh key?)" >&2
            failed=$((failed + 1)); continue
        fi
        count=$(git -C "$p" rev-list --count 'HEAD..@{u}' 2>/dev/null)
        ahead=$(git -C "$p" rev-list --count '@{u}..HEAD' 2>/dev/null)
        dirty=
        [ -z "$(git -C "$p" status --porcelain 2>/dev/null)" ] || dirty=" (uncommitted changes stay as they are)"
        if [ "${count:-0}" -eq 0 ]; then
            if [ "${ahead:-0}" -gt 0 ]; then
                echo "ok   $name: up to date, with $ahead commit(s) not pushed yet$dirty"
            else
                echo "ok   $name: already up to date$dirty"
            fi
            continue
        fi
        if [ "${ahead:-0}" -gt 0 ]; then
            echo "fail $name: $branch has diverged ($ahead commit(s) here, $count new on GitHub): merge or rebase it by hand" >&2
            failed=$((failed + 1)); continue
        fi
        if [ "$dry" -eq 1 ]; then
            echo "dry  $name: would pull $count commit(s) of $branch$dirty"; continue
        fi
        if out=$(git -C "$p" merge --ff-only -q '@{u}' 2>&1); then
            echo "pull $name: $count commit(s) of $branch$dirty"
            pulled=$((pulled + 1))
        else
            echo "fail $name: not pulled: $(printf '%s' "$out" | head -n 1) (nothing was changed)" >&2
            failed=$((failed + 1))
        fi
    done
    [ "$pulled" -eq 0 ] || echo "cursus: pulled $pulled project(s)"
    [ "$failed" -eq 0 ] || die "$failed project(s) could not be refreshed, see above"
}

cmd=${1:-}
[ $# -gt 0 ] && shift
case $cmd in
    init) init ;;
    update) update_projects ;;
    push) push_projects "$@" ;;
    refresh) refresh_projects "$@" ;;
    sort)
        for o in "$@"; do
            case $o in *=*) ;; *) die "expected name=track, got '$o'" ;; esac
            case " $tracks " in *" ${o#*=} "*) ;; *) die "unknown track '${o#*=}' (use: $tracks)" ;; esac
        done
        overrides="$*"
        sort_projects ;;
    *) echo "usage: cursus.sh init | sort [name=track ...] | update | push [name ...] | refresh [name ...]" >&2; exit 2 ;;
esac
