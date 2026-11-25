"""Everything the app reads from its environment, once, as one object that the composition root hands to whoever needs it."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    workspace: Path                      # sessions, the checks' work copies, the known_hosts of the clones
    projects: Path                       # the folder of projects, shared with the terminal container
    samples: Path                        # the subject library (samples/<track>/*.pdf and the Norm)
    progress_file: Path | None = None    # Progress.md, mounted as a file by compose; unset, recording a result is off
    terminal_url: str = ""
    terminal_token: str = ""
    scraper_url: str = ""                # the subject downloader (src/scraper_server.py); both unset, the library cannot download
    scraper_token: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        workspace = Path(env.get("WORKSPACE", "workspace")).resolve()
        samples = env.get("SAMPLES_DIR", "/samples" if Path("/samples").is_dir() else "samples")
        progress = env.get("PROGRESS_FILE")
        return cls(workspace=workspace, projects=Path(env.get("PROJECTS_DIR", workspace / "projects")).resolve(),
                   samples=Path(samples).resolve(), progress_file=Path(progress) if progress else None,
                   terminal_url=env.get("TERMINAL_URL", "").rstrip("/"), terminal_token=env.get("TERMINAL_TOKEN", ""),
                   scraper_url=env.get("SCRAPER_URL", "").rstrip("/"), scraper_token=env.get("SCRAPER_TOKEN", ""))

    @property
    def terminal_configured(self) -> bool:
        return bool(self.terminal_url and self.terminal_token)

    @property
    def scraper_configured(self) -> bool:
        return bool(self.scraper_url and self.scraper_token)
