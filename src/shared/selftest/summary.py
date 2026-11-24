"""The short answer drawn from the results of a self-test."""

from __future__ import annotations


def summarize(results: list[dict]) -> dict:
    failed = [r["name"] for r in results if not r["ok"] and r["required"]]
    docker_down = "docker daemon" in failed
    basics = [n for n in failed if not n.startswith("docker")]
    return {
        "ready": not failed,
        "failed": failed,
        "basics_ok": not basics,
        "docker_ok": not [n for n in failed if n.startswith("docker")],
        "docker_daemon_down": docker_down and "docker client" not in failed,
    }
