"""Settings: everything configurable, as one immutable object handed to whoever needs it."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Settings:
    login: str | None = None
    password: str | None = None
    samples_dir: Path = ROOT / "samples"
    artifacts_dir: Path = ROOT / "artifacts"
    data_dir: Path = DATA
    lang: str = "en"
    delay: float = 1.5
    headless: bool = True
    browser_channel: str = "chrome"
    with_artifacts: bool = True
    with_children: bool = True
    with_experience: bool = False
    state_file: Path = ROOT / ".session" / "state.json"
    user_agent_file: Path = ROOT / ".session" / "user_agent.txt"
    debug_dir: Path = ROOT / ".debug"

    @classmethod
    def from_env(cls, *, lang: str | None = None, delay: float | None = None, headed: bool = False,
                 with_artifacts: bool = True, with_children: bool = True, with_experience: bool = False) -> Settings:
        """Settings from the environment (the .env of the repository), letting command-line values win."""
        env = os.environ.get
        return cls(
            login=env("INTRA_LOGIN") or None,
            password=env("INTRA_PASSWORD") or None,
            samples_dir=Path(env("SAMPLES_DIR") or ROOT / "samples").expanduser(),
            artifacts_dir=Path(env("ARTIFACTS_DIR") or ROOT / "artifacts").expanduser(),
            lang=(lang or env("SUBJECT_LANG") or "en").lower(),
            delay=delay if delay is not None else float(env("SCRAPE_DELAY") or 1.5),
            headless=not headed and env("HEADLESS", "true").lower() != "false",
            browser_channel=env("BROWSER_CHANNEL", "chrome"),
            with_artifacts=with_artifacts, with_children=with_children, with_experience=with_experience,
        )
