"""Where a submodule may be downloaded from.

The addresses come from the project's .gitmodules, which someone else wrote: only these hosts (and the project's own) are contacted,
only over https without credentials, or over ssh (your agent) to a host on the list, and never a path, `ext::` or `--option`.
"""

from __future__ import annotations

import re

from verdict.repository.repo.address.urls import HOST, PATH, SCP_RE, SSH_RE, ssh_target

SUBMODULE_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org")
HTTPS = re.compile(rf"^https://(?P<host>{HOST})/{PATH}$")


class HostPolicy:
    """Strategy: which addresses a submodule may be downloaded from (the known hosts, and the project's own)."""

    def __init__(self, extra_hosts: frozenset[str] | set[str] = frozenset()) -> None:
        self.allowed = {h.lower() for h in SUBMODULE_HOSTS} | {h.lower() for h in extra_hosts}

    def source(self, url: str) -> str | None:
        """'https' or 'ssh' when `url` is an address a submodule may be downloaded from, None otherwise."""
        if ".." in url or url.startswith("-"):
            return None
        if (m := HTTPS.match(url)):
            return "https" if m["host"].lower() in self.allowed else None
        if SCP_RE.match(url) or SSH_RE.match(url):
            return "ssh" if ssh_target(url)[1].lower() in self.allowed else None
        return None


def submodule_source(url: str, extra_hosts: frozenset[str] | set[str] = frozenset()) -> str | None:
    """'https' or 'ssh' when `url` is an address a submodule may be downloaded from, None otherwise."""
    return HostPolicy(extra_hosts).source(url)
