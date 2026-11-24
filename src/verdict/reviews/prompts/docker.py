"""The Docker files a student ships, found among the paths of the repository."""

from __future__ import annotations

import re

DOC_EXTENSIONS = {"txt", "md", "pdf", "png", "jpg", "jpeg", "gif", "svg", "html", "rst", "doc", "docx", "bak", "orig", "swp"}


def find_docker_files(paths) -> list[str]:
    """Dockerfiles and compose files the student ships (top levels only, vendored folders ignored)."""
    found = []
    for raw in paths:
        path = str(raw).replace("\\", "/")
        parts = path.split("/")
        name = parts[-1].lower()
        if len(parts) > 4 or any(part in (".git", "node_modules", "mlx", "minilibx") for part in parts):
            continue
        is_dockerfile = name == "dockerfile" or name.endswith(".dockerfile") or (
            name.startswith("dockerfile.") and name.rsplit(".", 1)[1] not in DOC_EXTENSIONS)         # not notes like dockerfile.txt
        if is_dockerfile or re.fullmatch(r"(docker-)?compose(\..+)?\.ya?ml", name):
            found.append(path)
    return sorted(found, key=lambda x: (x.count("/"), x))[:12]
