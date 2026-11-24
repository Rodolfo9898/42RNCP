"""The outcome of one `make`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BuildResult:
    ok: bool
    log: str
    ran: bool = True
    needs_network: bool = False   # it failed while trying to download something, and the sandbox has no network
