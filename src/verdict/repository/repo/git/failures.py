"""What went wrong with a clone or a pull, in words, and whether trying once more may help."""

from __future__ import annotations

SIGN_IN_FAILED = "Permission denied (publickey"
# The signs of a server that answers differently from one connection to the next, rather than a key that is refused for good.
TRANSIENT = ("Permission denied (publickey", "Connection closed by", "Connection reset", "kex_exchange_identification",
             "Connection timed out", "Operation timed out")


def is_transient(stderr: str) -> bool:
    return any(sign in stderr for sign in TRANSIENT)


def explain_clone_failure(stderr: str, returncode: int) -> str:
    lines = [l.strip() for l in stderr.splitlines() if l.strip() and not l.startswith("Cloning into")]
    message = " | ".join(lines[-4:]) if lines else f"no error output (exit code {returncode})"
    hint = ""
    if SIGN_IN_FAILED in stderr or "Could not read from remote repository" in stderr:
        hint = (" — SSH could not authenticate. Check the 'ssh' indicator in the status bar: the container needs your "
                "ssh-agent with a key loaded (run `ssh-add` on your computer), and that key must have access to this repository.")
    elif "Host key verification failed" in stderr:
        hint = " — the host's SSH key is not trusted yet; remove workspace/known_hosts if the server's key changed."
    elif "Could not resolve hostname" in stderr:
        hint = " — the container has no DNS/network access to that host."
    return f"git clone failed: {message}{hint}"
