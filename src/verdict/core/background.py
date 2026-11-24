"""Starting work that outlives the request that asked for it."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

Spawn = Callable[..., None]


def in_thread(function: Callable[..., Any], *args: Any) -> None:
    """The default way: a daemon thread. Tests hand the services another `Spawn` that runs the work where they can see it."""
    threading.Thread(target=function, args=args, daemon=True).start()
