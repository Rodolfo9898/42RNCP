"""The addresses a repository may be cloned from: SSH only, and never something ssh could read as an option."""

from __future__ import annotations

import re

from verdict.repository.repo.model.errors import RepoError

# Accepted forms: git@host:owner/repo(.git)  and  ssh://git@host[:port]/owner/repo(.git)
# Host and user must not start with "-" (ssh would read them as options, e.g. -oProxyCommand=...).
USER = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
HOST = r"[A-Za-z0-9][A-Za-z0-9.-]*"
PATH = r"[\w.~][\w.~/-]*"
SCP_RE = re.compile(rf"^{USER}@{HOST}:{PATH}$")
SSH_RE = re.compile(rf"^ssh://{USER}@{HOST}(?::\d{{1,5}})?/{PATH}$")


def validate_url(url: str) -> str:
    url = url.strip()
    if not (SCP_RE.match(url) or SSH_RE.match(url)) or ".." in url:
        raise RepoError("Only SSH repository URLs are accepted, e.g. git@github.com:user/repo.git")
    return url


def ssh_target(url: str) -> tuple[str, str, int | None]:
    """(user, host, port) of an address that validate_url accepted."""
    if url.startswith("ssh://"):
        user, _, rest = url[len("ssh://"):].partition("@")
        authority = rest.split("/", 1)[0]
        host, _, port = authority.partition(":")
        return user, host, int(port) if port else None
    user, _, rest = url.partition("@")
    return user, rest.split(":", 1)[0], None
