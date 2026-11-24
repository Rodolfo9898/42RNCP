"""Where things are in the repository, for the tests (one place instead of a `Path(__file__).parent.parent` in every file)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DOCKER = ROOT / "docker"
SCRIPTS = ROOT / "scripts"
SAMPLES = ROOT / "samples"
EXTENSION = SRC / "extension"
