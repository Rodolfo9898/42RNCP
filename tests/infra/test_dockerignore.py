"""Each image has its own allow-list (docker/<image>/Dockerfile.dockerignore): everything its Dockerfile copies in must be on it,
and the folders that are not source (samples, projects, artifacts, secrets) must never be."""

import re

import pytest

from tests.paths import DOCKER, ROOT

IMAGES = sorted(p.parent.name for p in DOCKER.glob("*/Dockerfile"))
NEVER = ("samples", "projects", "artifacts", ".env", ".git", ".ssh-pub", ".session", "workspace")


def copied_sources(dockerfile: str) -> list[str]:
    """The paths the Dockerfile copies from the build context (COPY --from=... reads another stage, not the context)."""
    sources = []
    for line in re.sub(r"\\\n", " ", dockerfile).splitlines():
        words = line.split()
        if words[:1] == ["COPY"] and not any(w.startswith("--from=") for w in words):
            args = [w for w in words[1:] if not w.startswith("--")]
            sources += [w.rstrip("/").removeprefix("./") for w in args[:-1]]
    return sources


def allowed(path: str, ignore_lines: list[str]) -> bool:
    """Is `path` in the build context? Patterns are applied in order; the last one that matches wins (the forms used here: `*`, `!path`, `path`)."""
    inside = True
    for line in ignore_lines:
        if line == "*":
            inside = False
        elif line.startswith("!"):
            target = line[1:].rstrip("/")
            if path == target or path.startswith(target + "/"):
                inside = True
        elif "*" not in line and (path == line.rstrip("/") or path.startswith(line.rstrip("/") + "/")):
            inside = False
    return inside


def ignore_of(image: str) -> list[str]:
    text = (DOCKER / image / "Dockerfile.dockerignore").read_text()
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


@pytest.mark.parametrize("image", IMAGES)
def test_every_image_has_its_ignore_file_next_to_its_dockerfile(image):
    assert (DOCKER / image / "Dockerfile.dockerignore").is_file()
    assert not (ROOT / ".dockerignore").exists(), "one ignore file per image, beside its Dockerfile, not a shared one at the root"


@pytest.mark.parametrize("image", IMAGES)
def test_what_a_dockerfile_copies_in_is_on_its_allow_list(image):
    ignore = ignore_of(image)
    assert ignore[0] == "*", "an allow-list starts by leaving everything out"
    sources = copied_sources((DOCKER / image / "Dockerfile").read_text())
    assert sources, image
    for source in sources:
        assert (ROOT / source).exists(), f"{image}: COPY {source} does not exist"
        assert allowed(source, ignore), f"{image}: COPY {source} is left out of the build context by Dockerfile.dockerignore"


@pytest.mark.parametrize("image", IMAGES)
def test_nothing_that_is_not_source_can_reach_an_image(image):
    ignore = ignore_of(image)
    for folder in NEVER:
        assert not allowed(folder, ignore), f"{image}: {folder} is inside the build context"
        assert not allowed(f"{folder}/x", ignore), f"{image}: {folder}/x is inside the build context"


def test_the_extension_only_goes_into_the_terminal_image_and_never_into_the_python_wheel():
    assert allowed("src/extension/package.json", ignore_of("terminal"))
    assert not allowed("src/extension/package.json", ignore_of("web"))
    assert not allowed("src/extension/package.json", ignore_of("sandbox"))
