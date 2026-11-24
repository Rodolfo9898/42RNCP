"""What running the project's own Makefile in the sandbox gives, and why a failed build cannot always be judged."""

from __future__ import annotations

from pathlib import Path

from verdict.checks.context.build_result import BuildResult
from verdict.repository.repo import empty_submodules

NOTES_KEY = "submodule_notes"      # in the Ctx cache: what the web app tried when it downloaded the submodules ahead of the build


def offline_reason(repo: Path, notes: list, build: BuildResult) -> str:
    """Why a failed build cannot be judged: it needed the network (the sandbox has none) or submodules that were never downloaded.
    An empty string when the failure is the project's own. `notes` are the SubmoduleNote the app collected before the build."""
    if not build.ran:
        return ""
    # An empty submodule only explains a failure that talks about it (its folder, or something inside it that is missing):
    # a build that fails for the project's own reasons must stay a failure.
    empty = [p for p in empty_submodules(repo) if p in build.log or Path(p).name in build.log]
    if not (build.needs_network or empty):
        return ""
    tried = [n for n in notes if not n.ok]
    parts = ["The build could not be checked here: "
             + ("it tried to download something and the sandbox has no network on purpose." if build.needs_network
                else f"the submodule(s) {', '.join(empty)} are not downloaded, so the code they provide is missing.")]
    if tried:
        parts.append("The app tried to download the submodules ahead of the build and could not: "
                     + "; ".join(f"{n.path or 'submodules'}: {n.message}" for n in tried[:4]) + ".")
    elif empty:
        parts.append("The submodules are empty in the copy that is built.")
    parts.append("Build it yourself with the network on (⌨ Claude or ⌨ Shell in the project folder: `git submodule update --init`, then `make`) to settle this.")
    return " ".join(parts)
